//go:build windows

// EXPERIMENTAL: independently isolated Windows GUI lab ONLY.
// This helper is NOT authorized to run on the FotoMag production computer.
// It receives a validated target process plan as Base64URL(JSON) in argv[1],
// creates a separate, non-active Windows desktop, and launches the target on
// that desktop with the same inherited stdin/stdout/stderr pipes.
// An optional job object can kill only this helper's child tree on shutdown.
package main

import (
    "crypto/rand"
    "encoding/base64"
    "encoding/hex"
    "encoding/json"
    "errors"
    "fmt"
    "os"
    "path/filepath"
    "strings"
    "syscall"
    "unsafe"
)

const (
    desktopAllAccess = 0x000F01FF
    createNoWindow uint32 = 0x08000000
    createSuspended uint32 = 0x00000004
    startfUseStdHandles uint32 = 0x00000100
    startfUseShowWindow uint32 = 0x00000001
    swHide uint16 = 0
    jobObjectExtendedLimitInformation = 9
    jobObjectLimitKillOnJobClose uint32 = 0x00002000
    failureExitCode = 120
    maxEncodedPayload = 24000
)

type payload struct {
    Protocol int `json:"protocol"`
    Executable string `json:"executable"`
    Args []string `json:"args"`
    Verbatim bool `json:"verbatim"`
    KillTree bool `json:"killTree,omitempty"`
}

type basicLimitInformation struct {
    PerProcessUserTimeLimit int64
    PerJobUserTimeLimit int64
    LimitFlags uint32
    MinimumWorkingSetSize uintptr
    MaximumWorkingSetSize uintptr
    ActiveProcessLimit uint32
    Affinity uintptr
    PriorityClass uint32
    SchedulingClass uint32
}

type ioCounters struct {
    ReadOperationCount uint64
    WriteOperationCount uint64
    OtherOperationCount uint64
    ReadTransferCount uint64
    WriteTransferCount uint64
    OtherTransferCount uint64
}

type extendedLimitInformation struct {
    BasicLimitInformation basicLimitInformation
    IoInfo ioCounters
    ProcessMemoryLimit uintptr
    JobMemoryLimit uintptr
    PeakProcessMemoryUsed uintptr
    PeakJobMemoryUsed uintptr
}

var user32 = syscall.NewLazyDLL("user32.dll")
var kernel32 = syscall.NewLazyDLL("kernel32.dll")
var createDesktopW = user32.NewProc("CreateDesktopW")
var closeDesktop = user32.NewProc("CloseDesktop")
var createJobObjectW = kernel32.NewProc("CreateJobObjectW")
var assignProcessToJobObject = kernel32.NewProc("AssignProcessToJobObject")
var setInformationJobObject = kernel32.NewProc("SetInformationJobObject")
var resumeThread = kernel32.NewProc("ResumeThread")

func main() { os.Exit(run()) }

func run() int {
    _, hostErr := os.Hostname()
    if hostErr != nil || os.Getenv("GITHUB_ACTIONS") != "true" || os.Getenv("RUNNER_OS") != "Windows" || os.Getenv("RUNNER_ENVIRONMENT") != "github-hosted" {
        fail("production guard", errors.New("public GitHub-hosted Windows CI required"))
        return failureExitCode
    }
    // Deliberately separate from DC_WINDOWS_HEADLESS_BROKER. Merely setting
    // the feature flag cannot activate the binary outside an approved lab.
    if os.Getenv("FOTOMAG_ISOLATED_WINDOWS_LAB") != "YES" ||
       os.Getenv("FOTOMAG_VM_EVIDENCE_SAFE") != "YES" {
        fail("lab guard", errors.New("independent Windows lab gates not confirmed"))
        return failureExitCode
    }
    p, err := readPayload()
    if err != nil { fail("payload", err); return failureExitCode }

    // The desktop name contains no path separators. CreateDesktopW creates
    // it in the current window station, without switching the active desktop.
    name, err := uniqueDesktopName()
    if err != nil { fail("desktop nonce", err); return failureExitCode }
    desktopName, err := syscall.UTF16PtrFromString(name)
    if err != nil { fail("desktop name", err); return failureExitCode }
    hdesk, _, callErr := createDesktopW.Call(uintptr(unsafe.Pointer(desktopName)), 0, 0, 0, desktopAllAccess, 0)
    if hdesk == 0 { fail("CreateDesktopW", callErr); return failureExitCode }
    defer closeDesktop.Call(hdesk)

    handles, err := duplicateStandardHandles()
    if err != nil { fail("duplicate stdio", err); return failureExitCode }
    defer func(){ for _, h := range handles { syscall.CloseHandle(h) } }()

    var job syscall.Handle
    if p.KillTree {
        job, err = createOwnedJob()
        if err != nil { fail("job creation", err); return failureExitCode }
        defer syscall.CloseHandle(job)
    }

    commandLine := buildCommandLine(p)
    lpExe, err := syscall.UTF16PtrFromString(p.Executable)
    if err != nil { fail("executable UTF16", err); return failureExitCode }
    lpCommand, err := syscall.UTF16PtrFromString(commandLine)
    if err != nil { fail("command UTF16", err); return failureExitCode }
    // Windows STARTUPINFO.lpDesktop selects a different desktop without
    // SwitchDesktop. Child processes usually inherit their parent's desktop;
    // independent GUI brokers/COM launches may not and REQUIRE GUI tests.
    si := syscall.StartupInfo{}
    si.Cb = uint32(unsafe.Sizeof(si))
    si.Desktop = desktopName
    si.Flags = startfUseStdHandles | startfUseShowWindow
    si.ShowWindow = swHide
    si.StdInput = handles[0]
    si.StdOutput = handles[1]
    si.StdErr = handles[2]

    var pi syscall.ProcessInformation
    // Create suspended so a child cannot launch descendants before optional
    // job-object assignment. The helper has no relaunch/fallback code.
    creationFlags := createSuspended | createNoWindow
    err = syscall.CreateProcess(lpExe, lpCommand, nil, nil, true,
        creationFlags, nil, nil, &si, &pi)
    if err != nil { fail("CreateProcessW", err); return failureExitCode }
    defer syscall.CloseHandle(pi.Process)
    defer syscall.CloseHandle(pi.Thread)

    if p.KillTree {
        r, _, e := assignProcessToJobObject.Call(uintptr(job),uintptr(pi.Process))
        if r == 0 {
            syscall.TerminateProcess(pi.Process, failureExitCode)
            fail("AssignProcessToJobObject",e)
            return failureExitCode
        }
    }
    writeLabEvidence(name, uint32(os.Getpid()), pi.ProcessId)
    r, _, e := resumeThread.Call(uintptr(pi.Thread))
    if r == 0xFFFFFFFF {
        syscall.TerminateProcess(pi.Process, failureExitCode)
        fail("ResumeThread",e)
        return failureExitCode
    }

    event, err := syscall.WaitForSingleObject(pi.Process, syscall.INFINITE)
    if err != nil || event != syscall.WAIT_OBJECT_0 {
        // If wait fails, do not leave a child with an unobserved exit status.
        syscall.TerminateProcess(pi.Process, failureExitCode)
        fail("WaitForSingleObject",fmt.Errorf("event=%d err=%v",event,err))
        return failureExitCode
    }
    var exitCode uint32
    if err := syscall.GetExitCodeProcess(pi.Process, &exitCode); err != nil {
        fail("GetExitCodeProcess",err)
        return failureExitCode
    }
    return int(exitCode)
}

func writeLabEvidence(name string, brokerPID, childPID uint32) {
    dir := os.Getenv("FOTOMAG_LAB_EVIDENCE_DIR")
    if dir=="" {return}
    if err:=os.MkdirAll(dir,0700);err!=nil{return}
    nameOnly:=fmt.Sprintf("lab_pid_%d_%d.json",brokerPID,childPID)
    file,err:=os.OpenFile(filepath.Join(dir,nameOnly),os.O_WRONLY|os.O_CREATE|os.O_EXCL,0600)
    if err!=nil{return}
    defer file.Close()
    _=json.NewEncoder(file).Encode(map[string]any{"broker_pid":brokerPID,"target_pid":childPID,"hidden_desktop":name})
}

func fail(where string, err error) { fmt.Fprintf(os.Stderr, "FOTOMAG_HEADLESS_BROKER_ERROR[%s]: %v\n", where, err) }

func uniqueDesktopName() (string,error) {
    var n [12]byte
    if _, err := rand.Read(n[:]); err != nil { return "",err }
    return fmt.Sprintf("FMDCLab_%d_%s",os.Getpid(),hex.EncodeToString(n[:])),nil
}

func readPayload() (payload,error) {
    var p payload
    if len(os.Args)!=2 { return p,errors.New("expected exactly one encoded payload") }
    if len(os.Args[1])>maxEncodedPayload { return p,errors.New("payload length limit") }
    raw,err:=base64.RawURLEncoding.DecodeString(os.Args[1]); if err!=nil { return p,err }
    if err=json.Unmarshal(raw,&p);err!=nil{return p,err}
    if p.Protocol!=1 {return p,errors.New("unsupported protocol")}
    if !filepath.IsAbs(p.Executable)||!strings.EqualFold(filepath.Ext(p.Executable),".exe"){
        return p,errors.New("absolute EXE required")
    }
    if _,err:=os.Stat(p.Executable);err!=nil{return p,fmt.Errorf("target missing: %w",err)}
    for _,a:=range p.Args { if strings.ContainsRune(a,0) {return p,errors.New("NUL in argument")}}
    return p,nil
}

func duplicateStandardHandles() ([3]syscall.Handle,error) {
    var out [3]syscall.Handle
    ids:=[3]int{syscall.STD_INPUT_HANDLE,syscall.STD_OUTPUT_HANDLE,syscall.STD_ERROR_HANDLE}
    current,err:=syscall.GetCurrentProcess();if err!=nil{return out,err}
    for i,id:=range ids {
        h,err:=syscall.GetStdHandle(id)
        if err!=nil||h==0||h==syscall.InvalidHandle {
            for j:=0;j<i;j++{syscall.CloseHandle(out[j])}
            return out,fmt.Errorf("bad inherited stdio %d: %v",i,err)
        }
        if err=syscall.DuplicateHandle(current,h,current,&out[i],0,true,syscall.DUPLICATE_SAME_ACCESS);err!=nil{
            for j:=0;j<i;j++{syscall.CloseHandle(out[j])}
            return out,err
        }
    }
    return out,nil
}

func buildCommandLine(p payload) string {
    // For regular executables, use Windows/Go commandline escaping.
    // For CMD, mirror Node spawn(windowsVerbatimArguments:true), preserving
    // exactly the raw /c command string. Only a Windows GUI lab can verify
    // the exact semantics for unusual cmd quoting combinations.
    parts:=[]string{syscall.EscapeArg(p.Executable)}
    for _,a:=range p.Args {
        if p.Verbatim {parts=append(parts,a)}else{parts=append(parts,syscall.EscapeArg(a))}
    }
    return strings.Join(parts," ")
}

func createOwnedJob() (syscall.Handle,error) {
    r,_,e:=createJobObjectW.Call(0,0)
    if r==0{return 0,e}
    job:=syscall.Handle(r)
    lim:=extendedLimitInformation{}
    lim.BasicLimitInformation.LimitFlags=jobObjectLimitKillOnJobClose
    ok,_,err:=setInformationJobObject.Call(uintptr(job),jobObjectExtendedLimitInformation,
        uintptr(unsafe.Pointer(&lim)),unsafe.Sizeof(lim))
    if ok==0 {syscall.CloseHandle(job);return 0,err}
    return job,nil
}

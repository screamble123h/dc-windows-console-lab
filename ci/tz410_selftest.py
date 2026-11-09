"""Cross-platform pure tests; no Windows process spawn."""
from tz410_control_analysis import analyze_controls
from tz410_resource_audit import examine
from tz410_clixml_channels import classify
from tz410_final_verdict import verdict

P='TZ410_VISIBLE_POS_TEST'
N='TZ410_HIDDEN_NEG_TEST'
common=[{'event':'observer_start'}, {'event':'observer_done'}]
win={'event':'new_visible_console_window','time_utc':'2026-11-09T00:00:00Z',
     'window':{'hwnd':1000,'pid':2000,'class':'ConsoleWindowClass','title':P},
     'process':{'pid':2000,'ppid':123,'name':'conhost.exe'}}
focus={'event':'console_foreground_transition','window':{'title':P}}
r=analyze_controls([common[0],win,focus,common[1]],P,N,123,0,True)
assert r['positive']['status']=='PASS' and r['negative']['status']=='PASS'
assert r['focus']['status']=='PASS' and r['calibrated_for_zero_window_claim']
print('PASS positive window / focus / negative hidden synthetic fixture')
r=analyze_controls(common,P,N,123,0,True)
assert r['positive']['status']=='NOT_DETECTED' and not r['calibrated_for_zero_window_claim']
print('PASS missing positive blocks calibration')
r=analyze_controls([common[0],win,{**win,'window':{**win['window'],'title':N}},common[1]],P,N,123,0,True)
assert r['negative']['status']=='FAIL_OR_INCONCLUSIVE' and not r['calibrated_for_zero_window_claim']
print('PASS negative visible triggers fail')
r=analyze_controls([common[0],win,common[1]],P,N,123,0,False)
assert r['focus']['status']=='NOT_PROVEN' and not r['focus']['human_workstation_focus_certified']
print('PASS unavailable Notepad focus is not invented')
r=analyze_controls([common[0],{**win,'window':{**win['window'],'class':'Chrome_WidgetWin_1'},'process':{'name':'chrome.exe'}},common[1]],P,N,123,0,False)
assert r['positive']['status']=='NOT_DETECTED'
print('PASS browser title is not console')
for kind in ('progress','error','warning'):
    xml=('#< CLIXML\n<Objs xmlns="http://schemas.microsoft.com/powershell/2004/04">'
         '<Obj S="'+kind+'" /></Objs>').encode()
    assert classify(xml)['records'][kind]==1
print('PASS CLIXML progress/error/warning retained individually')
assert classify(b'ordinary stderr')['xml_found'] is False
print('PASS ordinary stderr retained')
res=examine({'window_station_desktops_enumerated':True,'broker_desktop_names':[],'candidate_processes':[]},
            {'window_station_desktops_enumerated':True,'broker_desktop_names':['FMDCLab_leak'],'candidate_processes':[]})
assert res['status']=='INCONCLUSIVE_OR_LEAK_CANDIDATE'
print('PASS hidden desktop leak candidate blocks claim')
v=verdict({'positive':{'status':'PASS'},'negative':{'status':'PASS'},'focus':{'status':'PASS'},'calibrated_for_zero_window_claim':True},
          {'attempted':15,'passed':15}, {'matrix':[{'test':'functional','exit':0},{'test':'tool_api','exit':0},{'test':'clixml','exit':0}]},res)
assert v['ready_to_deploy'] is False and v['verdict']=='НЕ ГОТОВ К ВНЕДРЕНИЮ'
print('PASS green CI cannot imply deployment approval')

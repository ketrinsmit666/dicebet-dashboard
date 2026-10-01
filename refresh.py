"""Rebuild snapshots from daily exports. Does not send data to GitHub."""
from pathlib import Path
import argparse,csv,json,re,shutil,subprocess,sys,tempfile,importlib.util
from build_alerts import build
ROOT=Path(__file__).resolve().parent

def refresh(input_dir,as_of):
 source=Path(input_dir)
 for name in ['late_ftd.csv','user_lifecycle.csv','pulsation.csv']:
  if not (source/name).exists():raise FileNotFoundError(f'Required export missing: {source/name}')
 with tempfile.TemporaryDirectory() as temp:
  temp=Path(temp);inputs=temp/'inputs';inputs.mkdir();output=temp/'site';output.mkdir()
  for name in ['late_ftd.csv','user_lifecycle.csv','pulsation.csv']:
   shutil.copyfile(source/name,inputs/name)
  shutil.copyfile(ROOT/'data/targets.csv',inputs/'targets.csv')
  for name in ['crm.csv','reactivation.csv']:
   if (source/name).exists():shutil.copyfile(source/name,inputs/name)
   else:(inputs/name).write_text('month,geo,metric,label,actual,unit,as_of\n')
  subprocess.run([sys.executable,str(ROOT/'reporting/build_portal.py'),'--input-dir',str(inputs),'--output',str(output),'--as-of',as_of],check=True)
  spec=importlib.util.spec_from_file_location('lifecycle',ROOT/'reporting/builders/retention/build_report.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  retention=module.aggregate(inputs/'user_lifecycle.csv',as_of)
  alerts=build(inputs/'user_lifecycle.csv',inputs/'late_ftd.csv',as_of,inputs/'pulsation.csv')
  html=(output/'index.html').read_text();actuals=json.loads(re.search(r'const rows=(.*?),names=',html).group(1))
  # All calculations succeed before any replacement. Files replaced individually.
  for name,data in [('retention_cube.json',retention),('alerts_cube.json',alerts),('actuals.json',actuals)]:
   dest=ROOT/'data'/name;tmp=dest.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')));tmp.replace(dest)
  for path in output.glob('*.html'):
   target=ROOT/'reporting/site'/path.name;temp_target=target.with_suffix('.tmp');shutil.copyfile(path,temp_target);temp_target.replace(target)
  print('Updated:',as_of)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--input-dir',required=True);p.add_argument('--as-of',required=True,help='Actual source snapshot date YYYY-MM-DD; that partial day is excluded');a=p.parse_args();refresh(a.input_dir,a.as_of)

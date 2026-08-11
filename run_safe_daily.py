import subprocess,sys,os
r=subprocess.run([sys.executable, os.path.join(os.getcwd(),'night_send_safe.py')],capture_output=True,text=True)
open(os.path.join(os.getcwd(),'safe_daily.log'),'a').write('=== '+__import__('datetime').datetime.now().isoformat()+' ===
'+r.stdout+'
'+r.stderr+'
')

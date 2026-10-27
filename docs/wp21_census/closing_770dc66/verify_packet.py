import re, os, hashlib, csv, json, subprocess, collections
R='/data/data/com.termux/files/home/Codey-OS/'
S='/data/data/com.termux/files/usr/tmp/wp21_closure_next/'
def sha(p): return hashlib.sha256(open(p,'rb').read()).hexdigest()
known={}
for base in (R+'docs/wp21_census/closing_770dc66/', R+'docs/wp21_census/'):
    for d,_,fs in os.walk(base):
        if 'handoff_2026' in d or 'replay_A' in d: continue
        for f in fs: p=os.path.join(d,f); known.setdefault(sha(p),p.replace(R,''))
for rel in ['replay_b1_subset.py','replay_b1_subset_cases.json','replay_va.py','replay_guard.py','frozen_source_manifest.json','classification_units/C5_FRESH3_dispositions.tsv.pre_round2_corrections','stale_register_adjudication.json','classification_units/stale_reconciliation_REVIEW.json','merged_candidate/packets/C1_reviewed_dispositions.tsv','merged_candidate/packets/C2_reviewed_dispositions.tsv','merged_candidate/packets/C3_reviewed_dispositions.tsv','merged_candidate/packets/C4_FRESH_reviewed_dispositions.tsv','merged_candidate/packets/C7_reviewed_dispositions.tsv','G15B_49_RECONCILIATION_FINAL.tsv.pre_rereview','census_frozen_1/scan.tsv']:
    known.setdefault(sha(S+rel),'scratch:'+rel)
for rel in ['tests/test_wp21_census.py','docs/security.md','docs/commands.md','docs/architecture.md']:
    known.setdefault(sha(R+rel),rel)
head=subprocess.run(['git','-C',R,'show','HEAD:docs/wp21_census/dispositions.tsv'],capture_output=True).stdout
known[hashlib.sha256(head).hexdigest()]='git HEAD:docs/wp21_census/dispositions.tsv'
files={'packet':R+'docs/WP2_1_CLOSING_PACKET_2026-10-27.md','README':R+'docs/wp21_census/closing_770dc66/README.md','PROJECT_LOG':R+'PROJECT_LOG.md','blueprint':R+'CODEY_OS_MASTER_BLUEPRINT.md','NEW_ISSUES':R+'NEW_ISSUES.md'}
hexre=re.compile(r'(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])')
bad=0
for name,p in files.items():
    txt=open(p,encoding='utf-8').read()
    if name in('PROJECT_LOG','blueprint','NEW_ISSUES'):
        # only text added by this pass: the 2026-10-27 closing entry / status paragraph / closing-pass bullets
        if name=='PROJECT_LOG': txt=txt.split('## 2026-10-26')[0]
        if name=='blueprint':
            i=txt.find('Status update (2026-10-27, closing packet'); txt=txt[i:i+6000]
        if name=='NEW_ISSUES': txt='\n'.join(l for l in txt.split('\n') if 'WP2.1 closing pass 2026-10-27' in l)
    hs=sorted(set(hexre.findall(txt)))
    for h in hs:
        ok=h in known
        bad+=not ok
        print(f'{name:11} {h[:12]}... {"OK  "+known[h] if ok else "NO MATCH"}')
    # 8-char prefixes elsewhere
print('FULL-HASH MISMATCHES:',bad)
# --- counts ---
reg=list(csv.DictReader(open(R+'docs/wp21_census/dispositions.tsv',newline=''),delimiter='\t',quoting=csv.QUOTE_NONE)) if False else None
import sys
sys.path.insert(0,R)
lines=open(R+'docs/wp21_census/dispositions.tsv',encoding='utf-8').read().split('\n')
hdr=None; rows=[]
for l in lines:
    if not l or l.startswith('#'): continue
    c=l.split('\t')
    if hdr is None and c[0]=='key': hdr=c; continue
    rows.append(dict(zip(hdr,c)))
print('register rows',len(rows),'header',hdr)
cc=collections.Counter(r['class'] for r in rows); print('class',dict(cc),'UNKNOWN',cc.get('UNKNOWN',0))
print('reviewed_by populated',sum(1 for r in rows if r.get('reviewed_by','').strip()))
print('UNMEDIATED rows',cc.get('UNMEDIATED'))
f=list(csv.DictReader(open(S+'G15B_49_RECONCILIATION_FINAL.tsv',newline=''),delimiter='\t'))
print('G15b cat',dict(collections.Counter(r['final_category'] for r in f)),'sev',dict(collections.Counter(r['severity_final'] for r in f)),'non-closed',sum(r['final_category']!='CLOSED_CODE_REVIEW' for r in f))
print('exactly-one trigger literal per non-closed row:',all(sum(v.count('trigger:') for v in r.values())==1 for r in f if r['final_category']!='CLOSED_CODE_REVIEW'))
import re as _re
p=fl=sk=sub=0
for l in open(S+'final_tests_gate/summary.txt'):
    if l.startswith('chunk '):
        for pat,k in((r'(\d+) passed','p'),(r'(\d+) failed','f'),(r'(\d+) skipped','s'),(r'(\d+) subtests passed','u')):
            m=_re.search(pat,l)
            if m:
                v=int(m.group(1))
                if k=='p':p+=v
                elif k=='f':fl+=v
                elif k=='s':sk+=v
                else:sub+=v
rr=open(S+'final_tests_gate/fg_rerun_chunk_29.log').read().strip().split('\n')[-1]
print('raw chunks: passed',p,'failed',fl,'skipped',sk,'subtests',sub,'| chunk29 foreground rerun:',rr)
c29=[l for l in open(S+'final_tests_gate/summary.txt') if l.startswith('chunk 29 ')][0]
c29p=int(_re.search(r'(\d+) passed',c29).group(1)); rer=int(_re.search(r'(\d+) passed',rr).group(1))
print('effective passed',p-c29p+rer,'= raw',p,'- chunk29 raw',c29p,'+ foreground rerun',rer,'; effective failed',fl-4)
now={l.split('FAILED ',1)[1].strip() for l in open(S+'final_tests_gate/failed_nodes_now.txt') if 'FAILED ' in l}
base=set(open(S+'final_tests_gate/base_ids.txt').read().split())
eff=now-{n for n in now if 'test_service_lifecycle_mechanics' in n}
print('effective failing nodes',len(eff),'subset of 10 baseline:',eff<=base,'| baseline node not failing this run:',sorted(base-eff))
print('failed nodes now',len(open(S+'final_tests_gate/failed_nodes_now.txt').read().split('\n'))-1,'lines incl. chunk-29/chunk-6; base_ids',len(open(S+'final_tests_gate/base_ids.txt').read().split()))
b=json.load(open(S+'merged_candidate/build_summary.json')); print('build_summary rows',b['rows'],'unknown',b['unknown'],b['class_counts'])
print('census runs identical:',all(sha(S+f'census_frozen_1/{n}')==sha(S+f'census_frozen_{k}/{n}') for n in ['cli_flags.tsv','dispositions.seed.tsv','env_names.tsv','manifest_scan.tsv','scan.tsv','shell_scan.tsv','summary.json'] for k in (2,3)))
print('HEAD vs origin/main:',subprocess.run(['git','-C',R,'rev-parse','HEAD','origin/main'],capture_output=True,text=True).stdout.split())

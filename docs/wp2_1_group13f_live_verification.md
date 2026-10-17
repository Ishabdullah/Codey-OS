# WP2.1 group 13f — independent owned embedding teardown verification

2026-10-16. **PASS**, first execution; no contradiction or retry. Approved whole-round-2 source remained unchanged. Frozen five-file source hashes appear literally before/after below; frozen diff SHA256 `b7e58f6d9b959afb44fd90d709b1172a639538aa1efaa04bd92afcad66dda145` was independently checked before the run.

Eight ordinary Python fixture children ran in dedicated sessions with retained actual Popen handles. No embedding/generation model was loaded. HOME, CODEY_STATE_DIR, configuration and audit environment were set to one disposable directory before module imports. Actual model start and production Popen were forbidden. Health, TCP-port probes, foreign occupant discovery/cleanup, urllib, real slot lookup/registration/admission/reservation/listing were forbidden. Slot release was a fake callback that asserted the associated actual child had already been reaped. The verifier manually attached each actual child to EmbedServer rather than invoking startup.

Observed cases:

- Normal TERM confirmed rc-15 and released the slot only after reap.
- A child that had acknowledged installing SIGTERM-ignore required KILL; final wait confirmed rc-9 before release. Test-instance stop bounds were shortened from production 5s to 0.15s for this lightweight fixture.
- Injected signal refusal retained the exact live Popen, existing slot, cleanup_pending and global singleton. Calling start while that refusal remained returned False, with all foreign lookup/new-spawn paths forbidden. Restoring the real owned signal method allowed retry, reap, release and singleton clearing.
- Injected wait refusal with signal deliberately suppressed retained the same live ownership/accounting/singleton state. Restoring real operations allowed cleanup retry. This verifies retention around a real child with injected failures; it is not an OS permission-denial reproduction.
- Injected accounting release I/O failure occurred after actual rc-15 reap: Popen cleared, exact slot ID/pending/singleton retained. Retried accounting release then cleared singleton.
- An already-reaped child required no getpgid or killpg; both were forbidden during stop.
- Non-owning adopted-observation detach released only the assigned observation ID; a borrowed/no-assigned-ID representation released nothing. No actual adoption/foreign-port lookup ran and no adopted PID was signaled.
- An actual closed Rich Console stream did not convert successful real-child reap/slot cleanup into failure.
- A separately owned innocent child remained alive throughout all cases, then was reaped in finally. All eight retained actual Popen handles were finally waited/reaped and their pipes closed.

The frozen source includes daemon/inference caller changes, but full daemon startup/shutdown, watchdog concurrency, inference fallback, singleton races and interruption semantics remain unit-test evidence. This run proves owned subprocess teardown mechanics and mocked accounting/adoption integration only. It does not prove model readiness, durable residency, admission behavior, foreign-port replacement identity safety, daemon-exit durability or survival of SIGKILL/host death. No real resource-gate store, service, live application database, network/cloud/credential, or real port was used. Existing accounted-but-exempt embedding policy is unchanged; no admission or eviction API was called.

The raw log was line-flushed and fsynced as observations were produced, including RAM baselines before assertions and final cleanup. Production logger also printed eight identical successful-stop diagnostics to tool stdout (`ℹ  Embed server stopped`); those console lines are not in the explicit durable event log below. The closed-console case deliberately had no printable success line. All substantive assertions/observations and before/after free output are preserved below. Raw temporary artifacts: `/data/data/com.termux/files/usr/tmp/wp21_13f_live_raw.log` and `/data/data/com.termux/files/usr/tmp/wp21_13f_live_harness.py`.

## Literal durable command/output

```text
COMMAND python3 /data/data/com.termux/files/usr/tmp/wp21_13f_live_harness.py
BEFORE free -h
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.2Gi       756Mi        65Mi       3.0Gi       3.6Gi
Swap:           15Gi       5.7Gi        10Gi

BEFORE sha256 66f173255f68dd9c9361ce1d282366e296804020807ce3e4c77a1f50d4540eb7 core/embed_server.py
BEFORE sha256 f4ecda9c8e154f60897d49f139f0cef64a2f196e22a3512c924ef885a931164e core/inference.py
BEFORE sha256 7bb203b4936b158799c3126f34d7b8c833bd97dfa9bd890d61fd9e5ab0592add core/daemon.py
BEFORE sha256 b7e0b05c5c41f5268ea3c55c2163caaa789521b3e43655b449f51b278388f97b tests/test_embed_owned_lifecycle.py
BEFORE sha256 4de3d49401d96e6590f10cdc920e07240a65a15c48cf564b8538f155549eeacc tests/test_loader_resource_gate.py
SPAWN owned pid=17146 dedicated_session=True ignore_term=False
SPAWN owned pid=17147 dedicated_session=True ignore_term=False
owned group signal pid=17147 sig=15
release slot=term associated_pid=17147 returncode=-15
CASE term pid=17147 rc=-15 handle_clear=True slot_clear=True pending=False
SPAWN owned pid=17148 dedicated_session=True ignore_term=True
owned group signal pid=17148 sig=15
owned group signal pid=17148 sig=9
release slot=force associated_pid=17148 returncode=-9
CASE force pid=17148 rc=-9 handle_clear=True slot_clear=True pending=False
SPAWN owned pid=17154 dedicated_session=True ignore_term=False
CASE signal refusal raised EmbedTeardownError
owned group signal pid=17154 sig=15
release slot=retry associated_pid=17154 returncode=-15
CASE retry pid=17154 rc=-15 singleton_clear=True
SPAWN owned pid=17155 dedicated_session=True ignore_term=False
CASE wait refusal raised EmbedTeardownError
owned group signal pid=17155 sig=15
release slot=wait-retry associated_pid=17155 returncode=-15
CASE wait retry pid=17155 rc=-15
SPAWN owned pid=17156 dedicated_session=True ignore_term=False
owned group signal pid=17156 sig=15
CASE accounting failure raised EmbedTeardownError
accounting debt pid=17156 rc=-15 handle_clear=True slot=accounting pending=True
release slot=accounting associated_pid=17156 returncode=-15
CASE accounting retry resolved
SPAWN owned pid=17157 dedicated_session=True ignore_term=False
pre-reaped pid=17157 rc=-15
release slot=dead associated_pid=17157 returncode=-15
CASE already-dead child reaped without PID/group lookup or signal
release slot=adopted-observation associated_pid=None returncode=None
CASE adopted detach own_observation=True releases=1 signals=0
CASE adopted detach own_observation=False releases=0 signals=0
SPAWN owned pid=17158 dedicated_session=True ignore_term=False
owned group signal pid=17158 sig=15
release slot=closed-console associated_pid=17158 returncode=-15
CASE real Rich closed stream pid=17158 rc=-15 cleanup_success=True
CASE innocent owned fixture survives pid=17146 alive=True
AFTER sha256 66f173255f68dd9c9361ce1d282366e296804020807ce3e4c77a1f50d4540eb7 core/embed_server.py
AFTER sha256 f4ecda9c8e154f60897d49f139f0cef64a2f196e22a3512c924ef885a931164e core/inference.py
AFTER sha256 7bb203b4936b158799c3126f34d7b8c833bd97dfa9bd890d61fd9e5ab0592add core/daemon.py
AFTER sha256 b7e0b05c5c41f5268ea3c55c2163caaa789521b3e43655b449f51b278388f97b tests/test_embed_owned_lifecycle.py
AFTER sha256 4de3d49401d96e6590f10cdc920e07240a65a15c48cf564b8538f155549eeacc tests/test_loader_resource_gate.py
FINALLY reaped owned pid=17146 rc=-15
FINALLY reaped owned pid=17147 rc=-15
FINALLY reaped owned pid=17148 rc=-9
FINALLY reaped owned pid=17154 rc=-15
FINALLY reaped owned pid=17155 rc=-15
FINALLY reaped owned pid=17156 rc=-15
FINALLY reaped owned pid=17157 rc=-15
FINALLY reaped owned pid=17158 rc=-15
AFTER free -h
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.2Gi       741Mi        65Mi       3.0Gi       3.6Gi
Swap:           15Gi       5.7Gi        10Gi

RESULT PASS; owned_handles=8; actual_group_signals=[(17147, 15), (17148, 15), (17148, 9), (17154, 15), (17155, 15), (17156, 15), (17158, 15)]; released=['term', 'force', 'retry', 'wait-retry', 'accounting', 'dead', 'adopted-observation', 'closed-console']
```

## Exact disposable harness

```python
import os, sys, tempfile, subprocess, hashlib, json, signal, select, traceback
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack

REPO=Path('/data/data/com.termux/files/home/Codey-OS')
RAW=Path('/data/data/com.termux/files/usr/tmp/wp21_13f_live_raw.log')
log=RAW.open('w', buffering=1)
def emit(message):
    log.write(str(message)+'\n'); log.flush(); os.fsync(log.fileno())
expected={
 'core/embed_server.py':'66f173255f68dd9c9361ce1d282366e296804020807ce3e4c77a1f50d4540eb7',
 'core/inference.py':'f4ecda9c8e154f60897d49f139f0cef64a2f196e22a3512c924ef885a931164e',
 'core/daemon.py':'7bb203b4936b158799c3126f34d7b8c833bd97dfa9bd890d61fd9e5ab0592add',
 'tests/test_embed_owned_lifecycle.py':'b7e0b05c5c41f5268ea3c55c2163caaa789521b3e43655b449f51b278388f97b',
 'tests/test_loader_resource_gate.py':'4de3d49401d96e6590f10cdc920e07240a65a15c48cf564b8538f155549eeacc'}
def hashes(phase):
    for name, want in expected.items():
        got=hashlib.sha256((REPO/name).read_bytes()).hexdigest()
        emit(f'{phase} sha256 {got} {name}'); assert got==want
real_popen=subprocess.Popen
children=[]; released=[]; signals=[]; failures=[]
real_getpgid=os.getpgid; real_killpg=os.killpg

def forbid(*a,**k): raise AssertionError('forbidden external effect')
def child(ignore=False, dead=False):
    code=('import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print("READY",flush=True); time.sleep(120)' if ignore else 'import time; print("READY",flush=True); time.sleep(120)')
    p=real_popen([sys.executable,'-u','-c',code],stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    children.append(p)
    readable,_,_=select.select([p.stdout],[],[],5)
    assert readable and p.stdout.readline()==b'READY\n'
    emit(f'SPAWN owned pid={p.pid} dedicated_session={real_getpgid(p.pid)==p.pid} ignore_term={ignore}')
    if dead:
        p.terminate(); p.wait(timeout=5); emit(f'pre-reaped pid={p.pid} rc={p.returncode}')
    return p

def guarded_getpgid(pid):
    assert any(p.pid==pid and p.poll() is None for p in children)
    return real_getpgid(pid)
def guarded_killpg(pid,sig):
    assert any(p.pid==pid and p.poll() is None for p in children)
    signals.append((pid,int(sig))); emit(f'owned group signal pid={pid} sig={int(sig)}')
    return real_killpg(pid,sig)

def attach(es,p,name):
    s=es.EmbedServer(); s.process=p; s._owned_session_pid=p.pid; s._slot_id=name; s._started=True; s._STOP_TIMEOUT_S=.15
    return s

def release(slot):
    p=next((p for p in children if getattr(p,'fixture_slot',None)==slot),None)
    emit(f'release slot={slot} associated_pid={p.pid if p else None} returncode={p.returncode if p else None}')
    if p is not None: assert p.returncode is not None
    released.append(slot); return True

emit('COMMAND python3 /data/data/com.termux/files/usr/tmp/wp21_13f_live_harness.py')
emit('BEFORE free -h\n'+subprocess.check_output(['free','-h'],text=True))
status='FAIL'
with tempfile.TemporaryDirectory(prefix='wp21-13f-live-') as tmp:
    root=Path(tmp)
    os.environ.update(HOME=str(root/'home'), CODEY_STATE_DIR=str(root/'state'), CODEY_CONFIG_PATH=str(root/'config.json'), CODEY_AUDIT_PATH=str(root/'audit.jsonl'), CODEY_DIR=str(REPO))
    (root/'home').mkdir(); (root/'config.json').write_text('{}')
    sys.path.insert(0,str(REPO))
    try:
        hashes('BEFORE')
        from core import embed_server as es
        with ExitStack() as st:
            st.enter_context(patch.object(es.subprocess,'Popen',forbid))
            st.enter_context(patch.object(es.os,'getpgid',guarded_getpgid))
            st.enter_context(patch.object(es.os,'killpg',guarded_killpg))
            for name in ('_check_health','_port_is_bound','_find_port_occupant_pid','_kill_port_occupant'):
                st.enter_context(patch.object(es.EmbedServer,name,forbid))
            st.enter_context(patch.object(es.urllib.request,'urlopen',forbid))
            for name in ('reserve_slot','can_admit','list_slots','register_slot','find_resident_slot'):
                st.enter_context(patch.object(es.rg,name,forbid))
            st.enter_context(patch.object(es.rg,'release_slot',release))
            innocent=child()
            for force in (False,True):
                p=child(ignore=force); name='force' if force else 'term'; p.fixture_slot=name
                s=attach(es,p,name); s.stop()
                emit(f'CASE {name} pid={p.pid} rc={p.returncode} handle_clear={s.process is None} slot_clear={s._slot_id is None} pending={s.cleanup_pending}')
                assert p.returncode==(-9 if force else -15) and s.process is None and s._slot_id is None and not s.cleanup_pending
                assert innocent.poll() is None
            # Wait failure occurs before signal delivery; no claimed reap.
            p=child(); p.fixture_slot='retry'; s=attach(es,p,'retry'); es._embed_server=s
            original_wait=p.wait
            with patch.object(s,'_signal_owned',side_effect=PermissionError('injected owned signal refusal')):
                try: es.stop_embed_server()
                except es.EmbedTeardownError: emit('CASE signal refusal raised EmbedTeardownError')
                else: raise AssertionError('cleanup refusal lost')
                assert p.poll() is None and s.process is p and s._slot_id=='retry' and s.cleanup_pending and es._embed_server is s
                # start() must retry existing owned cleanup, never foreign lookup/new Popen.
                assert s.start() is False
                assert s.process is p and p.poll() is None and 'retry' not in released
            es.stop_embed_server()
            emit(f'CASE retry pid={p.pid} rc={p.returncode} singleton_clear={es._embed_server is None}')
            assert p.returncode==-15 and es._embed_server is None and 'retry' in released
            # Actual wait exception after a controlled no-op signal leaves live child.
            p=child(); p.fixture_slot='wait-retry'; s=attach(es,p,'wait-retry'); es._embed_server=s
            with patch.object(s,'_signal_owned',lambda *a: None), patch.object(p,'wait',side_effect=PermissionError('injected wait refusal')):
                try: es.stop_embed_server()
                except es.EmbedTeardownError: emit('CASE wait refusal raised EmbedTeardownError')
                else: raise AssertionError('wait refusal lost')
                assert p.poll() is None and s.process is p and s._slot_id=='wait-retry' and s.cleanup_pending and es._embed_server is s
            es.stop_embed_server(); emit(f'CASE wait retry pid={p.pid} rc={p.returncode}')
            assert p.returncode==-15 and es._embed_server is None
            p=child(); p.fixture_slot='accounting'; s=attach(es,p,'accounting'); es._embed_server=s
            with patch.object(es.rg,'release_slot',side_effect=OSError('injected slot I/O failure')):
                try: es.stop_embed_server()
                except es.EmbedTeardownError: emit('CASE accounting failure raised EmbedTeardownError')
                else: raise AssertionError('accounting failure lost')
                emit(f'accounting debt pid={p.pid} rc={p.returncode} handle_clear={s.process is None} slot={s._slot_id} pending={s.cleanup_pending}')
                assert p.returncode==-15 and s.process is None and s._slot_id=='accounting' and s.cleanup_pending and es._embed_server is s
            es.stop_embed_server(); assert es._embed_server is None and 'accounting' in released
            emit('CASE accounting retry resolved')
            p=child(dead=True); p.fixture_slot='dead'; s=attach(es,p,'dead')
            with patch.object(es.os,'getpgid',forbid),patch.object(es.os,'killpg',forbid): s.stop()
            assert s.process is None and 'dead' in released
            emit('CASE already-dead child reaped without PID/group lookup or signal')
            # Observation registrations are mocked; no adoption lookup or foreign PID signal.
            for slot in ('adopted-observation',None):
                s=es.EmbedServer(); s._started=True; s._slot_id=slot
                before=len(released)
                with patch.object(es.os,'getpgid',forbid),patch.object(es.os,'killpg',forbid): s.stop()
                assert len(released)==before+(slot is not None) and s._slot_id is None
                emit(f'CASE adopted detach own_observation={slot is not None} releases={len(released)-before} signals=0')
            # Exercise actual logger with closed Rich stream after a real reap.
            import utils.logger as logger
            from rich.console import Console
            stream=(root/'closed-console').open('w'); closed_console=Console(file=stream); stream.close()
            p=child(); p.fixture_slot='closed-console'; s=attach(es,p,'closed-console')
            with patch.object(logger,'console',closed_console): s.stop()
            assert p.returncode==-15 and s.process is None and not s.cleanup_pending
            emit(f'CASE real Rich closed stream pid={p.pid} rc={p.returncode} cleanup_success=True')
            assert innocent.poll() is None
            emit(f'CASE innocent owned fixture survives pid={innocent.pid} alive=True')
        hashes('AFTER')
        status='PASS'
    except BaseException:
        emit('CONTRADICTION OR HARNESS FAILURE\n'+traceback.format_exc())
    finally:
        for p in children:
            try:
                if p.poll() is None:
                    p.terminate()
                    try: p.wait(timeout=3)
                    except subprocess.TimeoutExpired: p.kill(); p.wait(timeout=3)
                else: p.wait(timeout=3)
                emit(f'FINALLY reaped owned pid={p.pid} rc={p.returncode}')
            except BaseException:
                status='FAIL'; emit('FINALLY FAILURE\n'+traceback.format_exc())
            for stream in (p.stdout,p.stderr):
                if stream: stream.close()
        emit('AFTER free -h\n'+subprocess.check_output(['free','-h'],text=True))
        emit(f'RESULT {status}; owned_handles={len(children)}; actual_group_signals={signals}; released={released}')
log.close()
print(RAW.read_text())
sys.exit(0 if status=='PASS' else 1)
```

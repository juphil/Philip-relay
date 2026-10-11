"""Use the native app-server API to inspect skills/hooks without a model turn."""
import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path


def inspect(home, project, approve=False):
    env = dict(os.environ)
    env['CODEX_HOME'] = str(home)
    # Windows npm 설치판은 codex.cmd — Popen 은 확장자를 붙여 찾지 않으므로 which 로 실제 실행 파일을 고른다
    exe = shutil.which('codex') or 'codex'
    process = subprocess.Popen([exe, 'app-server', '--stdio'], env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding='utf-8', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    responses = queue.Queue()

    def reader():
        for line in process.stdout:
            try:
                responses.put(json.loads(line))
            except ValueError:
                pass

    threading.Thread(target=reader, daemon=True).start()
    seq = 0

    def call(method, params):
        nonlocal seq
        seq += 1
        process.stdin.write(json.dumps({'jsonrpc':'2.0', 'id':seq, 'method':method, 'params':params}) + '\n')
        process.stdin.flush()
        deadline = time.monotonic() + 30
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f'응답 시간 초과: {method}')
            result = responses.get(timeout=remaining)
            if result.get('id') == seq:
                if 'error' in result:
                    raise RuntimeError(result['error'])
                return result['result']

    try:
        call('initialize', {'clientInfo': {'name':'philip-runtime-check','version':'1.0'},
                            'capabilities': {'experimentalApi':True}})
        process.stdin.write('{"jsonrpc":"2.0","method":"initialized"}\n')
        process.stdin.flush()
        hooks = call('hooks/list', {'cwds':[str(project)]})['data'][0]
        reviewed = []
        if approve:
            # Caller must first review the exact installed definition and script.
            # Use the runtime's currentHash; never synthesize hashes or bypass trust.
            for hook in hooks['hooks']:
                if hook.get('pluginId') != 'philip@philip-relay':
                    continue
                if hook['trustStatus'] in ('trusted', 'managed'):
                    continue
                call('config/value/write', {
                    'keyPath': 'hooks.state.' + json.dumps(hook['key']) + '.trusted_hash',
                    'value': hook['currentHash'], 'mergeStrategy':'upsert'})
                reviewed.append(hook['key'])
            hooks = call('hooks/list', {'cwds':[str(project)]})['data'][0]
        skills = call('skills/list', {'cwds':[str(project)], 'forceReload':True})['data'][0]
        names = sorted(s['name'] for s in skills['skills'] if s['name'].startswith('philip:'))
        return {'home':str(home), 'skills':names, 'skill_errors':skills.get('errors',[]),
                'hook_errors':hooks.get('errors',[]), 'warnings':hooks.get('warnings',[]),
                'hooks':[{'key':h['key'],'trust':h['trustStatus'],'plugin':h.get('pluginId')} for h in hooks['hooks']],
                'reviewed':reviewed}
    finally:
        process.terminate()
        process.wait(timeout=10)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description='공식 API로 실제 스킬·훅 로딩 검증')
    parser.add_argument('--home',type=Path,default=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex'))))
    parser.add_argument('--project',type=Path,default=Path.cwd())
    parser.add_argument('--approve-reviewed-philip-hooks',action='store_true',help='사용자가 적용을 승인하고 설치된 훅 코드 검토가 끝난 경우에만 신뢰 등록')
    args=parser.parse_args()
    try:
        result = inspect(args.home.resolve(),args.project.resolve(),args.approve_reviewed_philip_hooks)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        expected = {'philip:' + p.name for p in (Path(__file__).resolve().parents[1] / 'skills').iterdir() if (p / 'SKILL.md').is_file()}
        hook_def = json.loads((Path(__file__).resolve().parents[1] / 'hooks/hooks.json').read_text(encoding='utf-8-sig'))
        expected_hooks = sum(len(row.get('hooks', [])) for rows in hook_def.get('hooks', {}).values() for row in rows)
        failed = (result['skill_errors'] or result['hook_errors'] or result['warnings']
                  or set(result['skills']) != expected
                  or sum(h['plugin'] == 'philip@philip-relay' for h in result['hooks']) != expected_hooks
                  or any(h['trust'] not in ('trusted', 'managed') for h in result['hooks'] if h['plugin'] == 'philip@philip-relay'))
        return 1 if failed else 0
    except (OSError, RuntimeError, TimeoutError, queue.Empty) as exc:
        print(f'로딩 검증 실패: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())

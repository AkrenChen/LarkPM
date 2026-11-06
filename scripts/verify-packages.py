import json
import os
import pathlib
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def request(process, method, **params):
    process.stdin.write(json.dumps({'method': method, 'params': params}, ensure_ascii=False) + '\n')
    process.stdin.flush()
    line = process.stdout.readline()
    if not line:
        raise AssertionError('Packaged backend exited without a response')
    response = json.loads(line)
    if 'error' in response:
        raise AssertionError(response['error'])
    return response['result']


def main():
    with tempfile.TemporaryDirectory(prefix='larkpm-packaged-') as directory:
        env = dict(os.environ, LARKPM_DATA_DIR=directory, PYTHONIOENCODING='utf-8')
        commands = [ROOT / 'src-tauri' / 'sidecar' / 'larkpm-backend.exe',
                    ROOT.parent / 'LinkinNotes' / 'build' / 'larkpm-bridge' / 'sidecar' / 'linkin-backend.exe']
        processes = []
        try:
            for command in commands:
                processes.append(subprocess.Popen([str(command)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                                  text=True, encoding='utf-8', env=env, creationflags=0x08000000))
            pm, linkin = processes
            project = request(pm, 'demo')['project']
            task = request(pm, 'snapshot', project=project)['tasks'][0]
            task = request(pm, 'link', id=task['id'], revision=task['revision'])
            linked = request(linkin, 'pm_snapshot')['tasks'][0]
            assert linked['id'] == task['id']
            updated = request(linkin, 'pm_edit', id=task['id'], revision=linked['revision'], patch={'title': 'Packaged bridge check', 'state': 'active'})
            current = next(t for t in request(pm, 'snapshot', project=project)['tasks'] if t['id'] == task['id'])
            assert current['title'] == 'Packaged bridge check' and current['state'] == 'active'
            updated = request(linkin, 'pm_save', id=task['id'], revision=updated['revision'],
                              patch={'owners': [{'id': 'first', 'name': 'First'}, {'id': 'second', 'name': 'Second'}]},
                              note='PRIVATE-NOTE-MUST-NOT-LEAK', note_revision=0)
            assert 'PRIVATE-NOTE-MUST-NOT-LEAK' not in json.dumps(request(pm, 'snapshot', project=project))
            assert request(linkin, 'pm_snapshot')['tasks'][0]['note'] == 'PRIVATE-NOTE-MUST-NOT-LEAK'
            request(pm, 'edit', id=task['id'], revision=updated['revision'], patch={'state': 'done'})
            assert request(linkin, 'pm_snapshot')['tasks'][0]['state'] == 'done'
            child = request(linkin, 'pm_branch', id=task['id'], title='Packaged local branch')
            assert child['source'] is None and child['linked'] and child['upstream'] == [task['id']]
            assert child['readiness'] == 'ready'
            print('Packaged LarkPM + LinkinNotes: bidirectional fields, completion, local branch and note isolation passed.')
        finally:
            for process in processes:
                process.stdin.close()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                process.stdout.close()
                process.stderr.close()


if __name__ == '__main__':
    main()

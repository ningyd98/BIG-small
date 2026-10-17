"""ROOT text/byte scope gate for R251 candidates and the exact R253 checkpoint relocation.
No product import, AST, compilation, SQL or runtime validation.
"""
from pathlib import Path
import hashlib
import json
import re
import difflib
import traceback

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
A = ROOT/'artifacts/research/process/20261004-ced-development/astra-rounds'
D = A/'round251-p6-t2-event3-entry-fence-continuation-20261017'
Q = A/'round253-p6-t2-checkpoint-prelock-read-candidate-20261017'
OUT = Q/'root-product-candidate-source-acceptance.json'
checks = []

def pin(path, raw=None):
    raw = path.read_bytes() if raw is None else raw
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())

def identity(row):
    return {k:row[k] for k in ('path','bytes','sha256')}

def fixed(row):
    p = Path(row['path'])
    b = p.read_bytes()
    if p.is_symlink() or pin(p,b)!=identity(row):
        raise ValueError('exact fixed input differs: '+str(p))
    return b

def read(path):
    return json.loads(path.read_bytes())

def save(path, value):
    b = (json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
    with path.open('xb') as f:
        f.write(b)
    if path.read_bytes()!=b:
        raise ValueError('exclusive metadata readback differs')
    return pin(path,b)

def check(name, value):
    checks.append(dict(name=name,ok=bool(value)))

def blocks(s):
    ms = list(re.finditer(r'^    def (\w+)\(',s,re.M))
    return {m[1]:s[m.start():ms[i+1].start() if i+1<len(ms) else len(s)] for i,m in enumerate(ms)}

def header(block):
    lines = block.splitlines(keepends=True)
    end = next(i for i,l in enumerate(lines) if l.rstrip().endswith(':'))
    return ''.join(lines[:end+1]).rstrip()

def main():
    plan = read(Q/'plan.json')
    review = read(Q/'root-source-review-contract.json')
    observation = read(D/'input-observation.json')
    for row in plan['inputs']:
        fixed(row)
    for pair in plan['before']:
        check('complete_before_archive',fixed(pair['original'])==fixed(pair['archive']))
    for row in observation['current_sources']:
        check('all27_original_bytes',fixed(row['original'])==fixed(row['physical']))
    for row in observation['protected']:
        fixed(row)
    old = read(D/'implementation/prepared-product-values.json')
    new = json.loads(fixed(review['values']))
    patch_raw = fixed(review['patch'])
    fixed(review['change_report'])
    for row in review['additional_fixed_inputs']:
        fixed(row)
    check('actual_full_review_records',bool(review['full72_source_table_actuals'])
          and bool(review['full_composite_patch_read_actuals'])
          and bool(review['corrected_method_read_actual']))
    check('exact72_inventory_identities',len(new['entries'])==72
          and {(x['path'],x['method']) for x in new['entries']}==
              {(x['path'],x['method']) for x in observation['writer_inventory']})
    target = plan['inventory_correction']['entry_identity']
    changed = [i for i,x in enumerate(old['entries']) if
               (x['path'],x['method'])==(target['path'],target['method'])]
    check('one_checkpoint_inventory_record',len(changed)==1)
    ei = changed[0]
    check('other71_inventory_objects_exact',all(x==new['entries'][i] for i,x in enumerate(old['entries']) if i!=ei))
    old_cas = blocks(fixed(plan['scope']['candidate_input']).decode())['compare_and_set_checkpoint']
    prefix = (
        '        existing = self.get_checkpoint(checkpoint_id)\n'
        '        if existing is None or existing.checkpoint_hash != expected_checkpoint_hash:\n'
        '            return False\n'
        '        h = new_checkpoint.checkpoint_hash or _checkpoint_hash(new_checkpoint)\n'
        '        saved = new_checkpoint.model_copy(update={"checkpoint_hash": h}, deep=True)\n'
        '        payload = saved.model_dump_json()\n')
    guard = '            '+old['entries'][ei]['arguments']['expression']+'\n'
    check('unique_exact_original_prefix_guard',old_cas.count(prefix)==old_cas.count(guard)==1)
    expected_cas = old_cas.replace(prefix,'',1).replace(
        guard,guard+''.join('    '+l for l in prefix.splitlines(keepends=True)),1)
    helper = (
        '\n\ndef _local_legacy_write_guard_unlocked(repository, name, args, kwargs) -> None:\n'
        '    """Fence a public legacy writer while its actual storage lock is held."""\n'
        '    if _local_target(repository, name, args, kwargs):\n'
        '        raise ValueError("operational task mutation requires the registered private publication scope")\n')
    reconstructed_patch = '*** Begin Patch\n'
    facts = []
    for change in new['changes']:
        original = fixed(change['before'])
        check('physical_full_original',original==fixed(change['physical_before']))
        candidate = fixed(change['candidate'])
        check('logical_after_pin',pin(Path(change['after']['path']),candidate)==identity(change['after'])
              and change['after']['path']==change['before']['path'])
        name = Path(change['before']['path']).stem
        before, after = original.decode(), candidate.decode()
        if name=='protocol':
            check('only_existing_target_guard_helper',after.count(helper)==1 and after.replace(helper,'',1)==before)
        else:
            before_blocks, after_blocks = blocks(before),blocks(after)
            selected = [x for x in new['entries'] if x['path']==change['before']['path']]
            check('exact36_actual_methods_'+name,len(selected)==36
                  and {x['method'] for x in selected}==set(observation['writer_names']))
            restored = after
            for entry in selected:
                method = entry['method']
                original_method, candidate_method = before_blocks[method],after_blocks[method]
                call = '            '+entry['arguments']['expression']+'\n'
                check('method_header_and_full_hash_'+name+'.'+method,
                      header(original_method)==header(candidate_method)==entry['signature']
                      and hashlib.sha256(original_method.encode()).hexdigest()==entry['original_method_sha256']
                      and hashlib.sha256(candidate_method.encode()).hexdigest()==entry['candidate_method_sha256'])
                check('unique_guard_before_declared_first_'+name+'.'+method,
                      candidate_method.count(call)==1
                      and candidate_method.split(call,1)[1].splitlines()[0].strip()==entry['first_effect_or_controlling_read'])
                lines = candidate_method.splitlines()
                lock_pos = next(i for i,l in enumerate(lines) if l.startswith('        with self._'))
                check('no_prelock_self_storage_reference_'+name+'.'+method,
                      not any('self.' in l for l in lines[:lock_pos]))
                normalized = candidate_method
                if name=='sqlite':
                    check('one_real_write_transaction_'+method,
                          '        with self._write_lock, self._conn:\n'
                          '            self._conn.execute("BEGIN IMMEDIATE")\n'+call in candidate_method
                          and candidate_method.count('self._conn.execute("BEGIN IMMEDIATE")')==1)
                    if method=='compare_and_set_checkpoint':
                        check('exact_R253_six_line_move',candidate_method==expected_cas)
                        normalized = old_cas
                    normalized = normalized.replace(call,'',1)
                    if '        with self._write_lock:\n' in original_method:
                        normalized = normalized.replace(
                            '        with self._write_lock, self._conn:\n'
                            '            self._conn.execute("BEGIN IMMEDIATE")\n',
                            '        with self._write_lock:\n',1)
                elif method=='mark_event_handled':
                    normalized = normalized.replace(
                        '        with self._lock:\n'+call+'            return event_id in self._events\n',
                        '        return event_id in self._events\n',1)
                else:
                    check('actual_memory_lock_before_guard_'+method,
                          '        with self._lock:\n'+call in candidate_method)
                    normalized = normalized.replace(call,'',1)
                check('original_entire_body_preserved_'+name+'.'+method,normalized==original_method)
                restored = restored.replace(candidate_method,original_method,1)
                facts.append(dict(path=entry['path'],method=method,source_only=True))
            imported = '    _local_legacy_write_guard_unlocked,\n'
            check('only_guard_import_outside_methods_'+name,restored.count(imported)==1
                  and restored.replace(imported,'',1)==before)
        diff = list(difflib.unified_diff(before.splitlines(keepends=True),after.splitlines(keepends=True),n=5))
        reconstructed_patch += '*** Update File: '+change['before']['path']+'\n'+''.join(
            '@@\n' if l.startswith('@@ ') else l for l in diff[2:])
    reconstructed_patch += '*** End Patch'
    check('complete_native_patch_exact_reconstruction',patch_raw==reconstructed_patch.encode())
    check('only_three_original_product_paths',len(new['changes'])==3
          and {x['before']['path'] for x in new['changes']}==
              set(read(D/'plan.json')['scope']['product_paths']))
    if any(not x['ok'] for x in checks):
        raise ValueError('candidate scope check failed')
    out = dict(round='R253',status='APPROVED_R251_THREE_FILE_NATIVE_APPLICATION_ONLY',
               source_review=review,changes=new['changes'],inventory=review['values'],
               patch=review['patch'],checks=checks,check_count=len(checks),
               source_entries72=facts,product_native_applied=False,runtime_release=False,
               original4slots_unspent=True,T2_complete=False,T12_complete=False)
    print(json.dumps(dict(status=out['status'],checks=len(checks),record=save(OUT,out)),ensure_ascii=False))

if __name__=='__main__':
    try:
        main()
    except BaseException as error:
        save(Q/'root-product-candidate-source-review-failure.json',
             dict(exception=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc()),
                  checks=checks,product_native_applied=False,runtime_release=False))
        raise

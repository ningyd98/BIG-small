"""CPU evidence gate, including actual runtime/config types; never loads weights."""
import copy
import importlib
import json
import sys
from enum import Enum, IntEnum
from pathlib import Path

HERE = Path(__file__).resolve().parent
R486 = HERE.parent / 'round486-taichu-no-think-best-profile-20261108'
sys.path.insert(0, str(R486 / 'implementation'))
codec = importlib.import_module(sys.argv[1])
import torch
from compressed_tensors.quantization import QuantizationStatus

class String(str): pass
class Integer(int): pass
class Real(float): pass
class Mapping(dict): pass
class Sequence(list): pass
class Tuple(tuple): pass
class Number(IntEnum): ONE = 1
class Unsupported(Enum): VALUE = 'value'


def main():
    output = HERE / sys.argv[2]
    output.mkdir(exist_ok=False)
    actual = {'torch': torch.__version__, 'statuses': list(QuantizationStatus)}
    # First assertion must reproduce R487's real scalar-subclass failure.
    assert json.loads(json.dumps(codec.normalize(actual))) == json.loads(json.dumps(actual))
    checks = ['actual TorchVersion and every QuantizationStatus encode with native values']
    fixtures = [actual, Mapping({String('k'): Sequence([String('v'), Integer(2), Real(1.5), Number.ONE,
                Tuple([False, None])])}), {None: 'none', True: 'yes', 2.5: 'real'}]
    for index, value in enumerate(fixtures):
        before = copy.deepcopy(value)
        target = output / ('native-' + str(index) + '.json')
        codec.write_evidence(target, value)
        assert json.loads(target.read_text()) == json.loads(json.dumps(value, allow_nan=False))
        assert value == before
    checks += ['native subclasses/keys match stdlib JSON; source unmodified', 'sidecar generated for native subclasses']
    sidecar = json.loads((output / 'native-0.json.serialization.json').read_text())
    assert any(e['json_pointer'] == '/torch' and e['native_base'] == 'str' for e in sidecar['representations'])
    sets = {'a/b': {'~k': frozenset(['b', 'a'])}, 'empty': set(), 'mixed': {1, '1', (2,3)}}
    before = copy.deepcopy(sets); events = []
    safe = codec.normalize(sets, events=events)
    assert safe == codec.normalize(sets) and sets == before
    assert safe['a/b']['~k'] == ['a', 'b'] and safe['empty'] == []
    assert any(e['json_pointer'] == '/a~1b/~0k' for e in events)
    codec.write_evidence(output / 'sets.json', sets)
    checks += ['set/frozenset deterministic order and escaped pointers', 'set values not mutated']
    cycle=[]; cycle.append(cycle)
    for name, value, exception in [('object', object(), TypeError), ('enum', Unsupported.VALUE, TypeError),
            ('key', {object():1}, TypeError), ('cycle', cycle, ValueError), ('nan', float('nan'), ValueError),
            ('inf', float('inf'), ValueError)]:
        target=output/(name+'.json')
        try: codec.write_evidence(target, value)
        except exception: assert not target.exists()
        else: raise AssertionError(name+' was accepted')
    checks.append('unknown objects/enum/keys/cycles/nonfinite rejected before output creation')

    from experiment_r487 import CACHE, mode_features, read, check_sources, base_versions
    from r478_adapter import prepare
    from transformers import AutoProcessor, CompressedTensorsConfig, GenerationConfig
    check_sources(); versions = base_versions()
    config, model_class, patterns, adapter = prepare()
    try:
        quantization = CompressedTensorsConfig.from_dict(config.quantization_config,
            use_optimized_inference=True, dequantize=False)
        config.quantization_config = quantization  # actual HfQuantizer.preprocess_model assignment
        config.dtype = torch.bfloat16
        generation = GenerationConfig.from_pretrained(str(CACHE), local_files_only=True)
        processor = AutoProcessor.from_pretrained(str(CACHE), trust_remote_code=True,
            local_files_only=True, use_fast=False)
        processor_values = {}
        for mode, enabled in [('ON',True),('OFF',False)]:
            _, evidence, _ = mode_features(processor, enabled)
            processor_values[mode] = evidence
        raw = CACHE/'actual/round486/run-base-r487'
        objects = {'run-state': {'torch':torch.__version__, 'cuda':torch.version.cuda,
            'capability':[8,9], 'base_68':versions, 'requests_started':0, 'inference_calls_started':0},
            'adapter':adapter, 'model-config':config.to_dict(), 'generation-config':generation.to_dict(),
            'loading-info-historical':read(raw/'loading-info.json'),
            'initial-inventory-historical':read(raw/'initial-inventory.json'),
            'processor-ON':processor_values['ON'], 'processor-OFF':processor_values['OFF'],
            'kernel-bindings':read(R486/'processor-base.json')['kernel_bindings']}
        from transformers.utils.loading_report import LoadStateDictInfo
        objects['actual-loader-field-types'] = LoadStateDictInfo(missing_keys=set(),
            unexpected_keys={'a'}, mismatched_keys={('w',(1,2),(2,1))}, error_msgs=[],
            conversion_errors={}, skipped_pp_keys=set()).to_dict()
        coverage=[]
        for name, value in objects.items():
            target=output/(name+'.json'); codec.write_evidence(target,value)
            assert json.loads(target.read_text()) == json.loads(json.dumps(codec.normalize(value),allow_nan=False))
            coverage.append({'evidence':name,'status':'PASS','source':'frozen actual R487 load' if name.endswith('historical') else 'actual CPU objects; no weights',
                'top_level_keys':sorted(value)})
    finally: model_class._keys_to_ignore_on_load_unexpected = patterns
    checks.append('all pre-generation evidence save categories encoded and roundtripped on CPU')
    failure_dir=output/'failure-injection'; failure_dir.mkdir()
    primary='PRIMARY: original runtime exception\n'
    success=codec.finalize_evidence({'bad':object()}, [failure_dir/'state.json'], failure_dir, primary)
    assert success is False
    assert (failure_dir/'secondary-evidence-error.txt').exists()
    assert primary in (failure_dir/'secondary-evidence-error.txt').read_text()
    checks.append('secondary evidence error preserves primary and returns failure')
    result={'status':'PASS','checks':checks,'coverage':coverage,'model_loads':0,'generation_calls':0,
        'boundary':'CPU config and historical inventory fixtures; not new loader/quality evidence',
        'cuda_context_initialized':torch.cuda.is_initialized()}
    (HERE/'cpu-gate.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'PASS','checks':len(checks),'coverage_categories':len(coverage),
        'model_loads':0,'generation_calls':0,'cuda_initialized':torch.cuda.is_initialized()}))

if __name__=='__main__': main()

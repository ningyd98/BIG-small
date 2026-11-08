"""Derive the quality-first comparison without altering any model responses."""
import csv, hashlib, json, statistics
from datetime import UTC, datetime
from pathlib import Path
HERE=Path(__file__).resolve().parent.parent; ROOT=HERE.parents[5]
CACHE=ROOT/'datasets/model-cache/zdtaichu5-9b-fp8-round473'
R489=HERE.parent/'round489-taichu-isolated-jit-headers-20261108'
def read(path): return json.loads(path.read_text())
def save(path,value):
 with path.open('x') as f: json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
 scores={name:read(HERE/('scores-'+name+'.json')) for name in ['base','fla']}
 runs={'base':read(HERE/'run-base-r488.json'),'fla':read(HERE/'run-fla-r489.json')}
 rows=[]; compatibility={}; raw_files=[]; groups=[]
 for profile,run in runs.items():
  assert run['status']=='EIGHT_REQUESTS_COMPLETED' and len(run['actual_requests'])==8
  assert run['requests_started']==run['inference_calls_started']==8
  assert run['schedule']==['ON','OFF','OFF','ON','ON','OFF','OFF','ON']
  assert run['compressed_load']=='PASS' and run['fp8_layer_count']==248
  assert all(a['fp8_weights_preserved'] for a in run['actual_requests'])
  assert scores[profile]['actual_generation_calls']==8
  raw=Path(run['actual_requests'][0]['raw_directory']).parent
  loading=read(raw/'loading-info.json'); inventory=read(raw/'initial-inventory.json')
  bindings=read(raw/'kernel-bindings.json')
  selected=all(any(v['module'].startswith('fla.') for v in bindings[name]['selected_implementations'])
      for name in ['torch_chunk_gated_delta_rule','torch_recurrent_gated_delta_rule'])
  assert selected==(profile=='fla')
  assert all(run['kernel_call_counts'][name]>0 for name in bindings)
  samples=[]
  for row in csv.reader((raw/'gpu-200ms.csv').read_text().splitlines()):
   if len(row)==4:
    try:samples.append(int(row[1].strip()))
    except ValueError:pass
  compatibility[profile]={'real_load':'PASS','loading_info':loading,'exact_fp8_layers':len(inventory['fp8_layers']),
    'all_parameters_gpu':inventory['all_parameters_cuda'],'fp8_kernel':inventory['use_fp8_kernel'],
    'model_load_s':run['model_load_s'],'all_requests_preserved_fp8':True,
    'fla_selected':selected,'effective_call_counts':run['kernel_call_counts'],
    'whole_gpu_peak_mib_200ms_sampling':max(samples),'sampling_includes_desktop':True,
    'base68_unchanged':len(run['base_68'])==68,'attention':run['effective_attention']}
  for mode,group in scores[profile]['groups'].items():
   attempts=[x for x in run['actual_requests'] if x['mode']==mode]
   assert len(attempts)==4
   assert all(x['input_tokens']==(1028 if mode=='ON' else 1030) for x in attempts)
   score_rows=[x for x in scores[profile]['results'] if x['mode']==mode]
   warm=[x for x in attempts if x['mode_warm_sample']]
   groups.append({'profile':profile,'thinking':mode,**group,
     'output_unique_sha256':sorted({x['raw_response_sha256'] for x in attempts}),
     'thinking_end_tokens':[x['tokens_through_think_end'] for x in attempts],
     'eos_terminated':sum(x['ended_with_eos'] for x in attempts),
     'warm_median_generation_seconds_per_output_token':statistics.median(x['generation_s']/x['output_tokens'] for x in warm),
     'peak_torch_reserved_bytes':max(x['torch_peak_reserved_bytes'] for x in attempts),
     'all_outputs_fenced':all(Path(x['raw_directory'],'raw-response.txt').read_text().startswith('```') for x in attempts),
     'coordinates_assessed':sum(x['strict_json'] for x in score_rows)})
  rows+=scores[profile]['results']
  for p in sorted(raw.rglob('*')):
   if p.is_file(): raw_files.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)})
 for mode in ['ON','OFF']:
  for run in runs.values():
   for attempt in [x for x in run['actual_requests'] if x['mode']==mode]:
    actual=read(Path(attempt['raw_directory'])/'processor.json')
    assert actual['features']==read(HERE/'processor-base.json')['modes'][mode]['features']
 eligible=[g for g in groups if g['all_four_quality_pass']]
 fastest=min(groups,key=lambda x:x['warm_median_end_to_end_s'])
 by={(g['profile'],g['thinking']):g for g in groups}
 base_on=by['base','ON']; base_off=by['base','OFF']; fla_off=by['fla','OFF']
 comparisons={'base_thinking_off_latency_reduction_percent':100*(1-base_off['warm_median_end_to_end_s']/base_on['warm_median_end_to_end_s']),
    'fla_vs_base_off_latency_reduction_percent_observational':100*(1-fla_off['warm_median_end_to_end_s']/base_off['warm_median_end_to_end_s']),
    'fastest_vs_base_on_latency_reduction_percent':100*(1-fastest['warm_median_end_to_end_s']/base_on['warm_median_end_to_end_s']),
    'kernel_attribution_limit':'OFF output length/content changed across runtimes; total latency gain cannot be attributed solely to kernel throughput'}
 result={'status':'SIXTEEN_CONTROLLED_REQUESTS_COMPLETED','created_at':datetime.now(UTC).isoformat(),
    'selection':'QUALITY_ELIGIBLE_PROFILE_FOUND' if eligible else 'NO_PROFILE_PASSED_QUALITY_GATE',
    'selected_profile':min(eligible,key=lambda x:x['warm_median_end_to_end_s'])['profile'] if eligible else None,
    'observational_fastest':{'profile':fastest['profile'],'thinking':fastest['thinking'],'warm_end_to_end_median_s':fastest['warm_median_end_to_end_s'],
       'qualified_for_recommendation':fastest['all_four_quality_pass']},
    'groups':groups,'comparisons':comparisons,'compatibility':compatibility,
    'model':'TaichuAI/ZDTaichu5.0-9B-FP8','gpu':'RTX 4070 Ti SUPER 16GB','weight_sha256':'c2b70d4aeaa499e4bc4a267332b0338cdfca685de448338ea5014fc3eaf0a07a',
    'actual_loads':4,'historical_evidence_failures_without_generation':2,'actual_model_generations':16,
    'per_group_repeats':4,'per_group_warm_samples':3,'distinct_scenes':1,'fixed_static_frame':True,
    'ttft':'NOT_MEASURED','depth_causal_use':'NOT_TESTED','formal_acceptance':'NOT_PERFORMED',
    'readiness_before_B':read(R489/'readiness-gates.json')['elapsed_s'],
    'raw_delivery':'full local raw/weights/SDK/wheels/headers/venv/JIT excluded; manifests are not a full remote reproduction package'}
 save(HERE/'comparison.json',result)
 save(HERE/'raw-manifest.local-data.json',{'local_raw_only':True,'files':raw_files,'source_runs':{k:sha(HERE/('run-base-r488.json' if k=='base' else 'run-fla-r489.json')) for k in runs}})
 fields=['profile','mode','index','mode_index','mode_warm_sample','input_tokens','output_tokens','generation_s','end_to_end_s','strict_json','quality_pass','localization_assessment','raw_response_sha256']
 with (HERE/'request-metrics.csv').open('x',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
 table=['| 运行环境 | 思考 | 输出 token | warm 端到端中位数 | 严格 JSON | 完整质量 |','|---|---|---:|---:|---:|---:|']
 for g in groups:
  table.append(f"| {'基础 PyTorch' if g['profile']=='base' else 'FLA-only'} | {'开启' if g['thinking']=='ON' else '关闭'} | {','.join(map(str,sorted(set(g['output_tokens']))))} | {g['warm_median_end_to_end_s']:.3f} 秒 | {g['strict_json']}/4 | {g['quality_passes']}/4 |")
 text=("# ZDTaichu FP8 思考开关与 FLA 对照结果\n\n"
   f"本次最快是 FLA-only + 关闭思考，warm 端到端中位数 {fastest['warm_median_end_to_end_s']:.3f} 秒。但四种配置均未达到 4/4 完整质量门槛，因此本轮没有可推荐正式接入的最佳配置。\n\n"+'\n'.join(table)+"\n\n"
   "同一 RTX 4070 Ti SUPER 16GB、同一官方 FP8 权重和固定 S01 RGB/深度可视化双图。每组重复 4 次；warm 为该组首次之后 3 次中位数，顺序 ON/OFF/OFF/ON/ON/OFF/OFF/ON。仅有一个静态场景，不估计泛化质量、稳定 p95 或统计显著性。\n\n"
   f"基础环境关闭思考缩短 {comparisons['base_thinking_off_latency_reduction_percent']:.1f}% 耗时；FLA 关闭思考相比基础关闭思考的观察耗时再缩短 {comparisons['fla_vs_base_off_latency_reduction_percent_observational']:.1f}%。后者输出由 194 变为 176 token，内容与坐标数字也改变，不能将全部差额归因于内核。\n\n"
   "开启思考的回答均达到 512 token 上限；关闭思考均正常结束，但完整原始回答带 Markdown JSON 围栏，严格解析拒绝。没有剥离围栏/思考、补全文本或修坐标。严格 JSON 未通过时坐标不可评分，不能把 0 hit 当成已测定位失败，也未证明关闭思考保留空间能力。\n\n"
   "两个环境都真实加载 248 个 FP8 GPU 层，原 ViTPatchLinear BF16 层与 SDPA 范围不变；全部 16 次生成后 FP8 保留。FLA 的两个 GDN 实现被选中并实际调用；causal-conv1d 仍用 PyTorch fallback，因此不是完整快速路径。原 68 包版本/来源均保留，FLA 两包安装在独立 overlay。\n\n"
   f"FLA 第一模型请求 {runs['fla']['actual_requests'][0]['end_to_end_s']:.3f} 秒，包含模型内核首次编译。之前另有 {result['readiness_before_B']:.3f} 秒的 driver/4096 元素数值/processor 就绪检查，已单列；该组不是全冷启动。TTFT 未测量。\n\n"
   "R487/R488 保留了两次生成前证据记录失败及实际 Astra 计划；集合与 JSON 原生字符串子类处理均有 CPU 证据。R489 只将匹配开发包解压到隔离缓存并以子进程 CPATH 引用，系统未安装新包；真实 CUDA/JIT 数值门槛通过后才执行 B。共 4 次 load、16 次生成，没有额外模型 warmup。\n\n"
   "软件兼容、真实模型运行、固定场景质量和正式研究验收分别记录；正式验收未执行，未进行硬件派发或闭环抓取。完整 raw、权重、wheel、headers、venv 和 JIT 留本地；提交的是脚本、计划、清单和派生报告，不是完整远端复现包。\n\n"
   "复核入口：comparison.json、request-metrics.csv、scores-base.json、scores-fla.json 与各轮 step-report。研发提交以已交付 8b4a88b 的模型测试分支为父，仅加入本轮明确 artifact；复用的关键源码已核对与当前 live 输入字节一致，共享工作区的其他改动不在交付内。\n")
 (HERE/'phase-summary.md').write_text(text)
 print(json.dumps({'selection':result['selection'],'observational_fastest':result['observational_fastest'],'comparisons':comparisons,'requests':16},ensure_ascii=False))
if __name__=='__main__': main()

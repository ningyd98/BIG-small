"""CPU gcc of original Triton driver C; never imports Torch/model/extension."""
import hashlib
import json
import os
import shutil
import subprocess
import sysconfig
from pathlib import Path


def cumulative(prior,current_started,cap):
    value=prior+current_started+1
    if value>cap:raise ValueError("cumulative budget exhausted")
    return value


def main():
    root=Path.cwd();r=root/"artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109";out=r/"candidates/06-groundingpi"
    jit=root/"datasets/model-cache/ordered-small-vlm-20261109/jit/06-groundingpi-r514"
    for name in ["preflight","triton","inductor","tmp"]:(jit/name).mkdir(parents=True,exist_ok=False)
    env=dict(os.environ);env["CUDA_VISIBLE_DEVICES"]="";env["CPATH"]=json.loads((r/"candidates/03-lens/invocation-01.json").read_text())["env_overrides"]["CPATH"]
    source=root/".venv-taichu-round473/runtime-b/lib/python3.12/site-packages/triton/backends/nvidia/driver.c"
    before=hashlib.sha256(source.read_bytes()).hexdigest();assert before=="439c1e886fa9eac7346d7523d03ba0a4c52aa4c9b518ea86d8659b5c07eb7dc9"
    copy=jit/"preflight/cuda_utils.c";copy.write_bytes(source.read_bytes());output=jit/"preflight"/("cuda_utils"+sysconfig.get_config_var("EXT_SUFFIX"))
    gcc=shutil.which("gcc");base=root/".venv-taichu-round473/runtime-b/lib/python3.12/site-packages/triton/backends/nvidia"
    argv=[gcc,str(copy),"-O3","-shared","-fPIC","-Wno-psabi","-o",str(output),"-l:libcuda.so.1","-L"+str(base/"lib"),"-L/lib/x86_64-linux-gnu","-I"+str(base/"include"),"-I"+str(jit/"preflight"),"-I/usr/include/python3.12"]
    process=subprocess.run(argv,env=env,capture_output=True,text=True,timeout=300)
    (jit/"preflight/gcc.stdout").write_text(process.stdout);(jit/"preflight/gcc.stderr").write_text(process.stderr);assert process.returncode==0
    dep=subprocess.run([gcc,"-M",str(copy),"-I"+str(base/"include")],env=env,capture_output=True,text=True,timeout=300)
    (jit/"preflight/includes.d").write_text(dep.stdout);assert dep.returncode==0 and "headers-round489/usr/include/python3.12/Python.h" in dep.stdout
    assert output.stat().st_size>0
    elf=subprocess.check_output(["readelf","-h",str(output)],text=True);assert "X86-64" in elf
    result={"status":"PASS","argv":argv,"CPATH":env["CPATH"],"returncode":process.returncode,"source_sha256":before,"output_sha256":hashlib.sha256(output.read_bytes()).hexdigest(),"extension_imported":False,"cuda_initialized":False,"model_calls":0,"gcc_sha256":hashlib.sha256(Path(gcc).read_bytes()).hexdigest(),"readelf":elf}
    with (out/"jit-preflight-r514.json").open("x") as stream:json.dump(result,stream,ensure_ascii=False,indent=2);stream.write("\n")
    print("GROUNDINGPI_ORIGINAL_C_CPU_COMPILE_PASS",flush=True)


if __name__=="__main__":main()

cd /home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall
export CUDA_VISIBLE_DEVICES= HIP_VISIBLE_DEVICES= ROCR_VISIBLE_DEVICES= OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall/src:/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall
ulimit -c 0
/usr/bin/timeout -k 3s 120s /home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall/.venv/bin/python /tmp/bigsmall-closure-sampled.VX1EYuC9/run.py -s -vv -o faulthandler_timeout=0 --tb=short -p no:cacheprovider --basetemp=/tmp/bigsmall-closure-sampled.VX1EYuC9/pytest --junitxml=/tmp/bigsmall-closure-sampled.VX1EYuC9/pytest.xml tests/test_operational_runtime_closure.py::test_private_startup_to_transaction_grounding\[memory\] 

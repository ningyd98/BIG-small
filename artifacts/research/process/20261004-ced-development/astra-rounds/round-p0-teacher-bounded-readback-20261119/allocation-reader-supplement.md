# 同轮补充：采集与动作分配数

第二次离线派生文件仍为空。辅助程序 read_diagnostic_corrected.py 第 36 行把 allocation-ledger.json 的 allocated_acquisition_ids 列表与 raw-artifacts.json 的 allocated_acquisitions 整数直接比较，后两处又对两个计数求 len。生产原件逐字段核对为 319 个 acquisition ID、计数 319；0 个 action span ID、计数 0。

延续父计划仅修辅助读回器。验证两个原计数为非负 int（排除 bool），各自 ID 列表类型、元素身份/唯一性及 len 与原采集、动作数相等。报告中直接写计数。根据生产 schema 核对原路径及绑定，对错误类型、重复 ID、数量不符分别拒绝。保全两份原脚本、空派生、原错误记录与源 SHA，另用新后缀两次独立读回；无需重新采集。其他来源、原 scope 拒绝例及有界诊断验收继承父计划。

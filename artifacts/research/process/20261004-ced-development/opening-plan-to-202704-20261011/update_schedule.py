from pathlib import Path
from hashlib import sha256
from zipfile import ZipFile
import json
from lxml import etree
from xml.sax.saxutils import escape

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
WORK = Path('/tmp/bigsmall-opening-plan-to-202704-20261011')
SOURCE = ROOT / 'output/doc/20261024-opening-application/开题申请_三项正文_20261024.docx'
OUTPUT = ROOT / 'output/doc/20261024-opening-application/开题申请_三项正文_20261024_计划至202704.docx'
CONTENT_SOURCE = Path('/tmp/bigsmall-opening-three-sections-20261011/content.json')
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
EXPECTED_SOURCE_SHA = 'c0d9f69fdecbeb6939e92033fd01d87d88a98744127526d14268e77c83254fc6'

schedule = [
    '2026年10月24日前：完成相关文献调研与开题材料撰写，明确系统需求、研究范围和评价指标；结合前期开发结果，梳理视觉感知、云端规划和机械臂执行之间的数据接口，完善总体设计，并于10月24日提交开题申请。',
    '2026年11月：完善端侧目标观测、时间信息管理和动作执行条件检查，完成云端接口、任务状态管理与控制器的联合调试；建立正常抓取、搬运和放置的基础闭环，开展基础能力测试，确定满足要求的周期监督基线。',
    '2026年12月：完成事件触发机制和云边协同决策模块，研究观测变化、风险约束与通信成本对决策的影响；针对遮挡、旧图像、云端响应迟到等情况进行测试，完善异步请求处理、任务状态更新和执行保护机制。',
    '2027年1月：完成异常识别与局部修复模块，验证重新观测、有限重试、云端重规划和安全停止等处理流程；开展系统联合调试，完善已完成步骤保护和重复执行防护，形成可用于对照实验的完整软件原型。',
    '2027年2月：固定系统配置、方法参数和实验流程，开展独立先导实验，确定正式实验所需样本量与运行预算，完成实验场景、数据记录及统计方法的准备，并检查实验流程的可重复性。',
    '2027年3月：开展正式对照实验、消融实验和异常恢复实验，统计任务成功率、云端请求次数、完成时间及资源占用，分析不同场景下的性能差异和失败原因；整理系统设计与实验结论，完成论文初稿。',
    '2027年4月：根据导师意见修改并定稿论文，完成系统演示、技术文档、实验材料及专利证明材料的整理与归档。计划于4月底前形成一套云边协同机械臂控制系统原型、一组可追溯的实验结果和一篇学位论文，完成研究工作与材料交付。后续评阅和答辩按照学院正式安排执行；各阶段在满足前序验证要求后推进。',
]

def digest(path):
    return sha256(path.read_bytes()).hexdigest()

assert digest(SOURCE) == EXPECTED_SOURCE_SHA, 'Source changed; stop before editing'
assert not OUTPUT.exists(), 'Preserve any existing output'
content = json.loads(CONTENT_SOURCE.read_text(encoding='utf-8'))
old_schedule = content['schedule']
assert len(old_schedule) == len(schedule) == 7
with ZipFile(SOURCE) as source_zip:
    original_xml = source_zip.read('word/document.xml')
    original_root = etree.fromstring(original_xml)
    original_text = original_root.xpath('//w:t/text()', namespaces=NS)
    for paragraph in old_schedule:
        assert original_text.count(paragraph) == 1
    edited_xml = original_xml
    for old, new in zip(old_schedule, schedule):
        old_bytes = escape(old).encode('utf-8')
        new_bytes = escape(new).encode('utf-8')
        assert edited_xml.count(old_bytes) == 1
        edited_xml = edited_xml.replace(old_bytes, new_bytes, 1)
    edited_root = etree.fromstring(edited_xml)
    new_text = edited_root.xpath('//w:t/text()', namespaces=NS)
    assert new_text == [schedule[old_schedule.index(t)] if t in old_schedule else t for t in original_text]
    for group in ['background', 'references', 'research']:
        for paragraph in content[group]:
            assert new_text.count(paragraph) == 1
    structural_tags = ['tblPr', 'tblGrid', 'sectPr', 'pPr', 'rPr']
    for tag in structural_tags:
        old_nodes = original_root.xpath(f'//w:{tag}', namespaces=NS)
        new_nodes = edited_root.xpath(f'//w:{tag}', namespaces=NS)
        assert [etree.tostring(n) for n in old_nodes] == [etree.tostring(n) for n in new_nodes]
    with ZipFile(OUTPUT, 'w') as output_zip:
        for info in source_zip.infolist():
            payload = edited_xml if info.filename == 'word/document.xml' else source_zip.read(info.filename)
            output_zip.writestr(info, payload)

with ZipFile(SOURCE) as source_zip, ZipFile(OUTPUT) as output_zip:
    assert source_zip.namelist() == output_zip.namelist()
    changed_parts = [name for name in source_zip.namelist() if source_zip.read(name) != output_zip.read(name)]
    assert changed_parts == ['word/document.xml']

assert '12月27日' not in ''.join(new_text)
assert '2027年4月' in ''.join(new_text)
assert '202611505816.9' in ''.join(new_text)
assert len(edited_root.xpath('//w:tbl', namespaces=NS)) == 3
content['schedule'] = schedule
WORK.mkdir(parents=True, exist_ok=True)
(WORK / 'content.json').write_text(json.dumps(content, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
verification = {
    'source': str(SOURCE), 'source_sha256': digest(SOURCE),
    'output': str(OUTPUT), 'output_sha256': digest(OUTPUT),
    'changed_package_parts': changed_parts,
    'changed_text_nodes': sum(a != b for a, b in zip(original_text, new_text)),
    'schedule_paragraphs': 7,
    'unchanged_background_research_references': True,
    'unchanged_all_paragraph_run_table_section_properties': True,
    'opening_date_preserved': '2026年10月24日前' in ''.join(new_text),
    'patent_preserved': True,
    'plan_end_april_2027': True,
    'obsolete_december_27_removed': True,
}
(WORK / 'verification.json').write_text(json.dumps(verification, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(verification, ensure_ascii=False, indent=2))

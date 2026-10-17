# 三项正文 Word 模板约定

Reference：/tmp/bigsmall-opening-application-20261011/开题报告-2101210559丁亚伟.docx
SHA256：b322171190e2ef86b4a649c9bea16913e7b1cd1db1d55e4e6a43c3ce9a33f0d7。
此前已逐页检查同一参考的8页，证据位于 /tmp/bigsmall-opening-application-20261011/template-reference-render；原始包清单位于同目录template-parts.json。原始附件.doc和参考副本均不修改。

用户本轮仅要求技术背景、研究、开发方案、进展计划，使用上一条回答已写好的三项正文；不使用原Markdown开题报告，不添加五项结构、个人资料或评审页。各内容存于content.json。文献由聊天链接转换为Word常规[1]—[3]引用及书目，正文内容和顺序保持。

模板body[19]的主表行5、6、7为三个正文槽，body[17]为标题模式。删除参考封面、校名、元信息和评审页；删除旧正文的EndNote域和可见图形。保留三个栏名和模板括号说明。仅标题和三个栏目可见。

A4 11906×16838twips，左右1800、上下1440，唯一sectPr字节保留；页眉页脚0，无额外装饰。表格tblPr/tblGrid逐字节保留，宽8763，grid468/180/360/1440/720/1980/3615；原黑色0.5pt单元格边框及左右108twips内距保持。中文宋体10.5pt，西文Times New Roman10.5pt，黑色；正文16pt行距，2.5pt段后，首行420twips，说明及书目无首行缩进；主标题15pt粗体居中，新增Title样式匹配原标题字体。

为避免已知长表栏名被跨页拆分，规划三页：第一页技术背景及书目；第二页研究方案至第三项关键问题末段；第三页续研究方案的验证、目标及可行性段落，再接进展计划。三个源表克隆保留grid/tblPr，表外无文字显式分页段控制；研究续行左栏为空，不重复可见栏目。各行自动扩展，删除旧内容的固定/最小行高，正文单元格上下3pt内距。沿用此前已验证的表外分页方式。

仅word/document.xml、word/styles.xml（增加Title）及docProps/core.xml（清除样例作者/标题）可改。其余包parts、rels、numbering、settings、fontTable、theme与未显示media逐字节不变。原样式定义保持，原唯一sectPr及所有表grid/tblPr保持。无TOC/PAGE等需刷新的保留域，无内容控件。

交付前render_and_diff产生独立目录，检查全部页面；核对三栏目、所有content.json段落各一次有序出现、专利名称与申请号、日期、无旧五项小标题或样例身份；保留原始参考SHA与包结构；不做产品代码修改、产品测试或新研究试验。

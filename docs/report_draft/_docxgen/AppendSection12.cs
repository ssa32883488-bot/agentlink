using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;
using A = DocumentFormat.OpenXml.Drawing;
using DW = DocumentFormat.OpenXml.Drawing.Wordprocessing;
using PIC = DocumentFormat.OpenXml.Drawing.Pictures;

// Usage: AppendSection12.exe <input.docx> <output.docx>
var input = args.Length > 0 ? args[0] : @"C:\Users\32081\Desktop\智能体互联技术报告.docx";
var output = args.Length > 1 ? args[1] : @"C:\Users\32081\Desktop\智能体互联技术报告.docx";
var imgDir = @"f:\code\智能体协议\outputs\custom-imagegen";

File.Copy(input, output + ".bak", overwrite: true);
if (!string.Equals(Path.GetFullPath(input), Path.GetFullPath(output), StringComparison.OrdinalIgnoreCase))
{
    File.Copy(input, output, overwrite: true);
}
else
{
    // edit in place via temp
    var tmp = output + ".tmp.docx";
    File.Copy(input, tmp, overwrite: true);
    output = tmp;
}

using (var doc = WordprocessingDocument.Open(output, true))
{
    var main = doc.MainDocumentPart ?? throw new Exception("no main");
    var body = main.Document.Body ?? throw new Exception("no body");

    // Find anchor: 参考文献
    Paragraph? anchor = null;
    foreach (var p in body.Elements<Paragraph>())
    {
        var t = p.InnerText ?? "";
        if (t.Contains("参考文献"))
        {
            anchor = p;
            break;
        }
    }
    if (anchor == null) throw new Exception("anchor 参考文献 not found");

    uint nextDocPropId = 10;
    void InsertBefore(OpenXmlElement el) => body.InsertBefore(el, anchor);

    InsertBefore(Heading("2. 作品目标定位", 2));

    InsertBefore(BodyPara(
        T("本作品定名为「采联 AgentLink」，核心研发目标是：基于 AIP 智能体互联开源参考实现（ACPs），遵循 GB/Z 185 系列国家标准，搭建面向工业采销场景的异构多智能体互联协同系统，使采购、供应、物流等业务智能体在统一协议平面上完成自动发现、跨端互联与可验证访问，并形成可演示、可部署的业务闭环。")
    ));

    InsertBefore(BodyPara(
        T("目标定位可概括为「目标三角」：硬性合规目标（梧桐平台全流程验证）、业务场景目标（异构采销六智能体协同）、技术与效益目标（跨云二次开发与可验证协同增效），三者相互支撑（见图5）。")
    ));

    InsertBefore(InsertImage(main, Path.Combine(imgDir, "sec12-goals-triangle.png"), 500, 281, nextDocPropId++, "图5"));
    InsertBefore(Caption("图5　作品目标定位三角"));

    // 硬性目标
    InsertBefore(Heading("（1）硬性目标与梧桐全流程验证要求", 3));
    InsertBefore(BodyPara(
        T("依据赛题必要验证场景，本作品硬性目标明确如下：成功接入梧桐智能体互联平台（https://wt.ioa.pub/），实现智能体自动发现与跨端访问；并在梧桐智能体科研平台完成注册、发现、互联、访问全流程验证，留存可核查的验证记录。对应到工程验收口径：")
    ));

    InsertBefore(SimpleTable(
        new[] { "验证环节", "目标要求", "本作品对应能力" },
        new[]
        {
            new[] { "注册", "智能体完成平台身份注册（AIC/ACS）", "六智能体 ACS 已提交，AIC 已审核回填并绑定端点" },
            new[] { "发现", "可被平台自动发现（ADP）", "采购侧经平台 Discovery 发现供应侧候选，支持强制刷新" },
            new[] { "互联", "跨端协议互联与业务调用（AIP）", "跨云 RPC 询价/回执；支持组群消息协同" },
            new[] { "访问", "产生可统计的访问留痕（AMP）", "Leader/Partner 双侧 Access/Message 上报与同任务对账" },
        }));
    InsertBefore(Caption("表2　梧桐必要验证场景与本作品对应关系"));

    InsertBefore(InsertImage(main, Path.Combine(imgDir, "sec12-wutong-four-steps.png"), 500, 281, nextDocPropId++, "图6"));
    InsertBefore(Caption("图6　梧桐平台必要验证全流程（注册→发现→互联→访问）"));

    InsertBefore(BodyPara(
        T("关于后台访问数据留存：赛题要求提交平台后台智能体访问量截图与互联交互记录。当前官方未开放访问量查询接口，本作品将「平台控制台人工截图留存」列为提交前硬门槛；与此同时，技术侧已具备 AMP Access/Message 双侧上报、Kafka 主题留痕及同 taskId 对账能力，可作为互联访问过程的工程证据，并与日后平台后台截图相互印证。未完成平台侧访问佐证前，不宣称已满足全部材料硬门槛。")
    ));

    // 业务场景
    InsertBefore(Heading("（2）业务场景与协同功能", 3));
    InsertBefore(BodyPara(
        T("计划落地场景为座椅零部件采销业务网络：采购方提出物料需求，多家供应方差异化报价，物流方提供运费与时效，最终形成可确认的订单草案。系统部署六枚业务智能体，刻意保持异构——采购/物流侧与供应侧分属不同云与实现栈，但统一经 AIP/ACPs 互通，以验证「栈不同、主体不同、仍可协作」（见图7）。")
    ));

    InsertBefore(SimpleTable(
        new[] { "智能体", "业务角色", "协同职责（摘要）" },
        new[]
        {
            new[] { "采购智能体A/B", "买方 Leader", "需求理解、平台发现、短名单 HITL、并行询价、比价与路径选择、订单草案" },
            new[] { "供应智能体A/B/C", "卖方 Partner", "差异化报价与促销策略、可选合入运费、议价/组群竞价响应" },
            new[] { "物流智能体", "运力 Partner", "运费/时效估算，支撑货运捆包与 TCO 比较" },
        }));
    InsertBefore(Caption("表3　六智能体角色与协同职责"));

    InsertBefore(InsertImage(main, Path.Combine(imgDir, "sec12-six-agents.png"), 500, 281, nextDocPropId++, "图7"));
    InsertBefore(Caption("图7　采销六智能体协同拓扑（跨云 + 协议平面）"));

    InsertBefore(BodyPara(
        T("可实现的协同功能（按可验收能力列出）：① 平台侧自动发现供应能力；② 人机协同短名单确认（HITL）；③ 多家并行询价与比价；④ 促销/门槛类议价方案推演；⑤ 可选组群竞价与 TCO 选商；⑥ 物流合入后的综合成本比较；⑦ 双边确认与订单激活；⑧ 协议平面访问留痕与任务级对账。")
    ));

    // 技术指标
    InsertBefore(Heading("（3）预期技术指标", 3));
    InsertBefore(BodyPara(
        T("在基于开源代码、遵循 AIP 标准搭建互联系统的前提下，预期技术指标如下（实测数据以联调与第五章为准）：")
    ));
    InsertBefore(SimpleTable(
        new[] { "类别", "预期指标" },
        new[]
        {
            new[] { "功能", "六体完成注册/发现/互联/访问链路；至少跑通「发现→询价→比价→确认」主路径；HITL 四态可用" },
            new[] { "性能", "支持对不少于 3 家供应方并行询价；发现与调用时延可记录；组群协同可冒烟通过" },
            new[] { "兼容性", "不改国标 ACS/AIC/ADP/AIP/AMP 报文结构；跨云 HTTPS RPC；供应侧可异构实现仍协议互通" },
            new[] { "可部署", "双云可部署；提供脚本化部署与联调取证路径；关键配置与 AIC 可追溯" },
        }));
    InsertBefore(Caption("表4　预期技术指标（功能/性能/兼容/可部署）"));

    // 效益与开源
    InsertBefore(Heading("（4）预期技术、社会效益与开源鼓励项", 3));
    InsertBefore(BodyPara(
        T("技术效益：形成「国标协议面不变、业务与编排可创新」的二次开发范式，验证跨云异构智能体在 AIP/ACPs 下的可发现、可互联与可对账访问，为标准化落地提供可复用工程样本。社会效益：面向采销信息差与高沟通成本场景，用智能体协同分担检索、初筛、询价与比价等环节，降低人对低含金量流程的投入，提升匹配效率与过程可追溯性。")
    ));
    InsertBefore(BodyPara(
        T("开源与分享（鼓励项）：本作品基于 AIP 开源社区配套实现开展开发，计划在条件具备时于 AtomGit / GitHub 的 AIP-PUB 社区进行代码开源、问题反馈与技术分享（https://atomgit.com/AIP-PUB、https://github.com/AIP-PUB）；并鼓励在梧桐智能体科研平台分享智能体、技能、工具或算法模块，以回馈标准与开源生态。")
    ));

    InsertBefore(BodyPara(
        T("综上，本作品以「采联 AgentLink」为载体，把 1.1 提出的「怎么通 / 通了如何协同」具体化为可验证目标：协议上对齐 AIP 与梧桐四步验证，业务上落地异构采销六体协同，工程上坚持开源二次开发与可部署、可取证。")
    ));

    main.Document.Save();
}

// if edited via tmp, move over original
var finalOut = args.Length > 1 ? args[1] : @"C:\Users\32081\Desktop\智能体互联技术报告.docx";
if (output.EndsWith(".tmp.docx", StringComparison.OrdinalIgnoreCase))
{
    File.Copy(output, finalOut, overwrite: true);
    File.Delete(output);
}
Console.WriteLine("Updated: " + finalOut);

// ---- helpers (duplicated minimal set) ----
static Paragraph Heading(string text, int level)
{
    var styleId = level <= 2 ? (level == 1 ? "Heading1" : "Heading2") : "Heading3";
    return new Paragraph(
        new ParagraphProperties(new ParagraphStyleId { Val = styleId }, new Indentation { FirstLine = "0" },
            new SpacingBetweenLines { Before = "200", After = "100", Line = "360", LineRule = LineSpacingRuleValues.Auto }),
        new Run(new RunProperties(
            new RunFonts { Ascii = "Times New Roman", HighAnsi = "Times New Roman", EastAsia = level <= 2 ? "黑体" : "楷体" },
            new Bold(), new FontSize { Val = level == 2 ? "28" : "24" }),
            new Text(text)));
}

static Run T(string text) => new Run(
    new RunProperties(new RunFonts { Ascii = "Times New Roman", HighAnsi = "Times New Roman", EastAsia = "宋体" }, new FontSize { Val = "24" }),
    new Text(text) { Space = SpaceProcessingModeValues.Preserve });

static Paragraph BodyPara(params OpenXmlElement[] runs)
{
    var p = new Paragraph(new ParagraphProperties(
        new Justification { Val = JustificationValues.Both },
        new SpacingBetweenLines { Line = "360", LineRule = LineSpacingRuleValues.Auto, After = "120" },
        new Indentation { FirstLine = "480" }));
    foreach (var r in runs) p.Append(r);
    return p;
}

static Paragraph Caption(string text) => new Paragraph(
    new ParagraphProperties(new Justification { Val = JustificationValues.Center }, new Indentation { FirstLine = "0" },
        new SpacingBetweenLines { After = "160", Line = "300", LineRule = LineSpacingRuleValues.Auto }),
    new Run(new RunProperties(
        new RunFonts { Ascii = "Times New Roman", HighAnsi = "Times New Roman", EastAsia = "宋体" }, new Bold(), new FontSize { Val = "21" }),
        new Text(text)));

const long EmuPerPixel96Dpi = 9525L;

static Paragraph InsertImage(MainDocumentPart mainPart, string imagePath, int widthPx, int heightPx, uint docPropId, string name)
{
    var imagePart = mainPart.AddImagePart(ImagePartType.Png);
    using (var stream = File.OpenRead(imagePath)) imagePart.FeedData(stream);
    string relId = mainPart.GetIdOfPart(imagePart);
    long cx = widthPx * EmuPerPixel96Dpi;
    long cy = heightPx * EmuPerPixel96Dpi;
    var element = new Drawing(
        new DW.Inline(
            new DW.Extent { Cx = cx, Cy = cy },
            new DW.EffectExtent { LeftEdge = 0L, TopEdge = 0L, RightEdge = 0L, BottomEdge = 0L },
            new DW.DocProperties { Id = docPropId, Name = name },
            new DW.NonVisualGraphicFrameDrawingProperties(new A.GraphicFrameLocks { NoChangeAspect = true }),
            new A.Graphic(new A.GraphicData(
                new PIC.Picture(
                    new PIC.NonVisualPictureProperties(
                        new PIC.NonVisualDrawingProperties { Id = 0U, Name = Path.GetFileName(imagePath) },
                        new PIC.NonVisualPictureDrawingProperties()),
                    new PIC.BlipFill(new A.Blip { Embed = relId }, new A.Stretch(new A.FillRectangle())),
                    new PIC.ShapeProperties(
                        new A.Transform2D(new A.Offset { X = 0L, Y = 0L }, new A.Extents { Cx = cx, Cy = cy }),
                        new A.PresetGeometry(new A.AdjustValueList()) { Preset = A.ShapeTypeValues.Rectangle }))
            ) { Uri = "http://schemas.openxmlformats.org/drawingml/2006/picture" }))
        {
            DistanceFromTop = 0U, DistanceFromBottom = 0U, DistanceFromLeft = 0U, DistanceFromRight = 0U
        });
    return new Paragraph(
        new ParagraphProperties(new Justification { Val = JustificationValues.Center }, new Indentation { FirstLine = "0" },
            new SpacingBetweenLines { Before = "160", After = "40" }),
        new Run(element));
}

static Table SimpleTable(string[] headers, string[][] rows)
{
    var table = new Table(
        new TableProperties(
            new TableWidth { Width = "5000", Type = TableWidthUnitValues.Pct },
            new TableBorders(
                new TopBorder { Val = BorderValues.Single, Size = 4, Color = "666666" },
                new BottomBorder { Val = BorderValues.Single, Size = 4, Color = "666666" },
                new LeftBorder { Val = BorderValues.Single, Size = 4, Color = "666666" },
                new RightBorder { Val = BorderValues.Single, Size = 4, Color = "666666" },
                new InsideHorizontalBorder { Val = BorderValues.Single, Size = 4, Color = "AAAAAA" },
                new InsideVerticalBorder { Val = BorderValues.Single, Size = 4, Color = "AAAAAA" })),
        new TableGrid(headers.Select(_ => new GridColumn { Width = "2000" })));

    var hr = new TableRow();
    foreach (var h in headers)
        hr.Append(Cell(h, true));
    table.Append(hr);
    foreach (var r in rows)
    {
        var tr = new TableRow();
        foreach (var c in r) tr.Append(Cell(c, false));
        table.Append(tr);
    }
    return table;
}

static TableCell Cell(string text, bool header) => new TableCell(
    new TableCellProperties(
        header ? new Shading { Val = ShadingPatternValues.Clear, Fill = "E8EEF5" } : new Shading { Val = ShadingPatternValues.Clear, Fill = "FFFFFF" },
        new TableCellVerticalAlignment { Val = TableVerticalAlignmentValues.Center }),
    new Paragraph(
        new ParagraphProperties(new Indentation { FirstLine = "0" }, new SpacingBetweenLines { Before = "40", After = "40" }),
        new Run(new RunProperties(
            new RunFonts { EastAsia = header ? "黑体" : "宋体", Ascii = "Times New Roman", HighAnsi = "Times New Roman" },
            header ? new Bold() : null!,
            new FontSize { Val = "20" }),
            new Text(text) { Space = SpaceProcessingModeValues.Preserve })));

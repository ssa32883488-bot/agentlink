using System.Text;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;
using A = DocumentFormat.OpenXml.Drawing;
using DW = DocumentFormat.OpenXml.Drawing.Wordprocessing;
using PIC = DocumentFormat.OpenXml.Drawing.Pictures;

Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);

var outputPath = args.Length > 0
    ? args[0]
    : Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..",
        "1.1_行业与技术背景_插图版.docx"));

Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
if (File.Exists(outputPath)) File.Delete(outputPath);

using (var doc = WordprocessingDocument.Create(outputPath, WordprocessingDocumentType.Document))
{
    var main = doc.AddMainDocumentPart();
    main.Document = new Document();
    var body = main.Document.AppendChild(new Body());

    // Styles
    var stylesPart = main.AddNewPart<StyleDefinitionsPart>();
    stylesPart.Styles = BuildStyles();

    // Title
    body.Append(Heading("一、作品概述", 1));
    body.Append(Heading("1. 行业与技术背景", 2));

    // 现状
    body.Append(BodyPara(
        T("人工智能正从感知理解迈向生成决策与自主执行，智能体已成为赋能千行百业的重要载体"),
        Cite("1"),
        T("。产业对多智能体投入上升，但已部署方案中真正采用多智能体形态的比例仍偏低（约17%）"),
        Cite("2"),
        T("，说明「单点智能」与「跨主体协同」之间仍有落差。")
    ));

    // Web演进 → 智能体互联（精简，不复述概念教材）
    body.Append(BodyPara(
        T("借用业界常用的Web 1.0/2.0/3.0分析框架"),
        Cite("19"),
        Cite("20"),
        T("：Web 1.0侧重人从网络单向获取信息；Web 2.0转向用户参与、平台连接与信息大规模生产。信息量随之激增，而人的处理能力并未同步提升，甄别、沟通与决策负担加重。大模型在数据、算法与算力等多因素推动下提升了信息处理能力；当其接入工具与业务系统后，Agent开始替人完成整理需求、信息初筛、信息积累等任务。但不同主体各自部署Agent后，若缺少统一发现与互信交互机制，仍无法跨系统协作——智能体互联正是补齐这一环的关键方向（见图1）。Berners-Lee亦曾展望由软件代理分担流程繁琐、人专注决策与创意"),
        Cite("21"),
        T("；对本作品而言，重点不在重定义「互联网3.0」，而在探索不同业务主体如何在保留自主性的同时，通过共同协议实现Agent协作。")
    ));

    var imgDir = @"f:\code\智能体协议\outputs\custom-imagegen";
    // display width ~500px, keep 1672x941 aspect → height ≈ 281
    const int figW = 500;
    const int figH = 281;

    body.Append(InsertImageParagraph(main, Path.Combine(imgDir, "fig1-web-evolution.png"), figW, figH, 1U, "图1"));
    body.Append(CaptionPara("图1　从Web演进到智能体互联（分析框架示意）"));

    body.Append(StageTable());
    body.Append(CaptionPara("表1　能力递进对照"));

    // 异构痛点
    body.Append(Heading("（1）异构互通与协同落地痛点", 3));
    body.Append(BodyPara(
        T("异构智能体在身份、能力描述、发现、交互与工具调用上缺乏统一规范，适配成本高、协同效率低、可信管理难"),
        Cite("7"),
        T("；MCP、A2A、ANP等国际协议各有侧重，生态仍碎片化"),
        Cite("8"),
        Cite("9"),
        Cite("4-6"),
        T("。落地层面突出表现为：协议异构使人充当桥接；身份与权限难统一导致关键业务不敢跨主体委托；多轮协商与工具调用使Demo易、生产难"),
        Cite("2"),
        T("。采销网络中信息差长期存在，平台曝光又推高甄别、沟通、信任与决策成本；各方即便有AI，技术栈与接口不通则仍无法直连——亟需可互信、可发现、可协作的互联底座（见图2）。")
    ));
    body.Append(InsertImageParagraph(main, Path.Combine(imgDir, "fig2-hetero-pain.png"), figW, figH, 2U, "图2"));
    body.Append(CaptionPara("图2　异构智能体协同落地痛点示意"));

    // AIP / ACPs
    body.Append(Heading("（2）国家标准AIP与ACPs开源底座", 3));
    body.Append(BodyPara(
        T("我国已发布GB/Z 185—2026《人工智能 智能体互联》系列标准，覆盖身份、描述、发现、交互与工具调用等闭环"),
        Cite("13"),
        Cite("14"),
        Cite("1"),
        T("。北邮刘军等提出的ACPs协议族面向智能体互联网的注册、发现、交互与工具调用，并指出既有协议偏场景化、难单独支撑规模化互联"),
        Cite("10"),
        Cite("11"),
        T("。公开说明进一步明确：AIP国标以ACPs为重要共识基础，ACPs代码为AIP开源社区首套参考实现"),
        Cite("15"),
        Cite("7"),
        T("；梧桐平台据此提供注册、发现、互联与访问验证"),
        Cite("18"),
        T("。标准与开源已具备可接入条件，关键转向真实异构业务的协同实证（见图3）。")
    ));
    body.Append(InsertImageParagraph(main, Path.Combine(imgDir, "fig3-aip-acps.png"), figW, figH, 3U, "图3"));
    body.Append(CaptionPara("图3　国家标准AIP与ACPs开源底座"));

    // 必要性
    body.Append(Heading("（3）本作品的必要性与意义", 3));
    body.Append(BodyPara(
        T("综上，智能体互联已进入「标准确立、开源可用、平台可验」窗口，但仍缺场景化验证。本作品以AIP国标及ACPs开源实现为基线，面向采销异构多智能体场景，验证发现、互信互联与协同交互：技术上落实国标闭环的工程可落地性；实践上分担信息甄别与初步沟通等成本，并完成梧桐全流程验证。一句话：协议解决「怎么通」，本作品回答「通了之后如何协同增效」（见图4）。")
    ));
    body.Append(InsertImageParagraph(main, Path.Combine(imgDir, "fig4-necessity.png"), figW, figH, 4U, "图4"));
    body.Append(CaptionPara("图4　本作品问题—标准—目标逻辑链"));

    // 参考文献（本节引用）
    body.Append(Heading("参考文献（本节）", 2));
    string[] refs =
    {
        "[1] 新华社. 《人工智能 智能体互联》系列7项国家标准发布[EB/OL]. 中国政府网, 2026-06-26.",
        "[2] ISG. State of the Agentic AI Market Report[R]. 2025.",
        "[4] ABI Research. Can A2A and MCP … Solve … Multi-Agent Systems?[R/OL]. 2025.",
        "[5] Futurum Research. Agentic AI Open Standards Report: 1H-2025[R]. 2025.",
        "[6] Gartner. Innovation Insight: AI Agent Communication Protocols[R]. 2025.",
        "[7] 开放原子开源基金会. AIP开源项目在AtomGit正式开源[EB/OL]. 2026-07-07.",
        "[8] Ehtesham A, et al. A survey of agent interoperability protocols[J/OL]. arXiv:2505.02279, 2025.",
        "[9] Collaborative Agentic AI Needs Interoperability Across Ecosystems[J/OL]. arXiv:2505.21550, 2025.",
        "[10] Liu J, et al. ACPs: Agent Collaboration Protocols for the Internet of Agents[J/OL]. arXiv:2505.13523, 2025.",
        "[11] 刘军, 等. ACPs：面向智能体互联网的智能体协作协议体系[EB/OL]. 2025.",
        "[13] GB/Z 185.1—2026～185.7—2026 人工智能 智能体互联[S]. 2026.",
        "[14] 【国标详解】「四问+一图」读懂《人工智能 智能体互联》系列标准[EB/OL]. 2026.",
        "[15] 刘军. 北邮ACPs协议和代码与智能体互联AIP标准的关系[EB/OL]. 2025.",
        "[18] 梧桐智能体互联平台[EB/OL]. https://wt.ioa.pub/",
        "[19] O’Reilly T. What Is Web 2.0[EB/OL]. O’Reilly Media, 2005.",
        "[20] Berners-Lee T. Web 3.0 and Linked Data[EB/OL]. W3C, 2009.",
        "[21] Berners-Lee T. Realising the Full Potential of the Web[EB/OL]. W3C, 1998.",
    };
    foreach (var r in refs)
        body.Append(RefPara(r));

    // Section properties (A4)
    body.Append(new SectionProperties(
        new PageSize { Width = 11906, Height = 16838 },
        new PageMargin
        {
            Top = 1440,
            Bottom = 1440,
            Left = 1440U,
            Right = 1440U,
            Header = 851U,
            Footer = 992U,
            Gutter = 0U
        }
    ));

    main.Document.Save();
}

Console.WriteLine("Wrote: " + outputPath);

// ---------- helpers ----------

static Styles BuildStyles()
{
    var styles = new Styles();
    styles.Append(new DocDefaults(
        new RunPropertiesDefault(
            new RunProperties(
                new RunFonts { Ascii = "Times New Roman", HighAnsi = "Times New Roman", EastAsia = "宋体", ComplexScript = "Times New Roman" },
                new FontSize { Val = "24" }, // 小四 12pt
                new FontSizeComplexScript { Val = "24" }
            )
        ),
        new ParagraphPropertiesDefault(
            new ParagraphProperties(
                new SpacingBetweenLines { Line = "360", LineRule = LineSpacingRuleValues.Auto, After = "0", Before = "0" }
            )
        )
    ));

    styles.Append(MakeStyle("Normal", "正文", StyleValues.Paragraph, true,
        rPr: new RunProperties(
            new RunFonts { Ascii = "Times New Roman", HighAnsi = "Times New Roman", EastAsia = "宋体" },
            new FontSize { Val = "24" }
        ),
        pPr: new ParagraphProperties(
            new Justification { Val = JustificationValues.Both },
            new SpacingBetweenLines { Line = "360", LineRule = LineSpacingRuleValues.Auto, After = "120" },
            new Indentation { FirstLine = "480" }
        )));

    styles.Append(MakeStyle("Heading1", "标题 1", StyleValues.Paragraph, false,
        rPr: new RunProperties(
            new RunFonts { Ascii = "Times New Roman", HighAnsi = "Times New Roman", EastAsia = "黑体" },
            new Bold(), new BoldComplexScript(),
            new FontSize { Val = "32" } // 三号
        ),
        pPr: new ParagraphProperties(
            new SpacingBetweenLines { Before = "240", After = "120", Line = "360", LineRule = LineSpacingRuleValues.Auto },
            new OutlineLevel { Val = 0 }
        ), uiPriority: 1));

    styles.Append(MakeStyle("Heading2", "标题 2", StyleValues.Paragraph, false,
        rPr: new RunProperties(
            new RunFonts { Ascii = "Times New Roman", HighAnsi = "Times New Roman", EastAsia = "黑体" },
            new Bold(), new BoldComplexScript(),
            new FontSize { Val = "28" } // 四号
        ),
        pPr: new ParagraphProperties(
            new SpacingBetweenLines { Before = "200", After = "100", Line = "360", LineRule = LineSpacingRuleValues.Auto },
            new OutlineLevel { Val = 1 }
        ), uiPriority: 2));

    styles.Append(MakeStyle("Heading3", "标题 3", StyleValues.Paragraph, false,
        rPr: new RunProperties(
            new RunFonts { Ascii = "Times New Roman", HighAnsi = "Times New Roman", EastAsia = "楷体" },
            new Bold(), new BoldComplexScript(),
            new FontSize { Val = "24" }
        ),
        pPr: new ParagraphProperties(
            new SpacingBetweenLines { Before = "160", After = "80", Line = "360", LineRule = LineSpacingRuleValues.Auto },
            new OutlineLevel { Val = 2 }
        ), uiPriority: 3));

    return styles;
}

static Style MakeStyle(string id, string name, StyleValues type, bool isDefault,
    RunProperties? rPr = null, ParagraphProperties? pPr = null, int uiPriority = 0)
{
    var style = new Style { Type = type, StyleId = id, Default = isDefault ? true : null };
    style.Append(new StyleName { Val = name });
    if (uiPriority > 0) style.Append(new UIPriority { Val = uiPriority });
    style.Append(new PrimaryStyle());
    if (pPr != null) style.Append(new StyleParagraphProperties(pPr.Elements().Select(e => (OpenXmlElement)e.CloneNode(true))));
    if (rPr != null) style.Append(new StyleRunProperties(rPr.Elements().Select(e => (OpenXmlElement)e.CloneNode(true))));
    return style;
}

static Paragraph Heading(string text, int level)
{
    var styleId = level switch { 1 => "Heading1", 2 => "Heading2", _ => "Heading3" };
    return new Paragraph(
        new ParagraphProperties(new ParagraphStyleId { Val = styleId }, new Indentation { FirstLine = "0" }),
        new Run(
            new RunProperties(
                new RunFonts { Ascii = "Times New Roman", HighAnsi = "Times New Roman", EastAsia = level <= 2 ? "黑体" : "楷体" },
                new Bold(),
                new FontSize { Val = level == 1 ? "32" : level == 2 ? "28" : "24" }
            ),
            new Text(text) { Space = SpaceProcessingModeValues.Preserve }
        )
    );
}

static Run T(string text) => new Run(
    new RunProperties(
        new RunFonts { Ascii = "Times New Roman", HighAnsi = "Times New Roman", EastAsia = "宋体" },
        new FontSize { Val = "24" }
    ),
    new Text(text) { Space = SpaceProcessingModeValues.Preserve }
);

const long EmuPerPixel96Dpi = 9525L;

static Paragraph InsertImageParagraph(
    MainDocumentPart mainPart, string imagePath, int widthPx, int heightPx, uint docPropId, string name)
{
    var ext = Path.GetExtension(imagePath).ToLowerInvariant();
    var partType = ext switch
    {
        ".png" => ImagePartType.Png,
        ".jpg" or ".jpeg" => ImagePartType.Jpeg,
        ".webp" => ImagePartType.Png,
        _ => ImagePartType.Png
    };
    var imagePart = mainPart.AddImagePart(partType);
    using (var stream = File.OpenRead(imagePath))
        imagePart.FeedData(stream);
    string relId = mainPart.GetIdOfPart(imagePart);
    long cx = widthPx * EmuPerPixel96Dpi;
    long cy = heightPx * EmuPerPixel96Dpi;

    var element = new Drawing(
        new DW.Inline(
            new DW.Extent { Cx = cx, Cy = cy },
            new DW.EffectExtent { LeftEdge = 0L, TopEdge = 0L, RightEdge = 0L, BottomEdge = 0L },
            new DW.DocProperties { Id = docPropId, Name = name },
            new DW.NonVisualGraphicFrameDrawingProperties(
                new A.GraphicFrameLocks { NoChangeAspect = true }),
            new A.Graphic(
                new A.GraphicData(
                    new PIC.Picture(
                        new PIC.NonVisualPictureProperties(
                            new PIC.NonVisualDrawingProperties { Id = 0U, Name = Path.GetFileName(imagePath) },
                            new PIC.NonVisualPictureDrawingProperties()),
                        new PIC.BlipFill(
                            new A.Blip { Embed = relId },
                            new A.Stretch(new A.FillRectangle())),
                        new PIC.ShapeProperties(
                            new A.Transform2D(
                                new A.Offset { X = 0L, Y = 0L },
                                new A.Extents { Cx = cx, Cy = cy }),
                            new A.PresetGeometry(new A.AdjustValueList()) { Preset = A.ShapeTypeValues.Rectangle }))
                )
                { Uri = "http://schemas.openxmlformats.org/drawingml/2006/picture" })
        )
        {
            DistanceFromTop = 0U,
            DistanceFromBottom = 0U,
            DistanceFromLeft = 0U,
            DistanceFromRight = 0U
        });

    return new Paragraph(
        new ParagraphProperties(
            new Justification { Val = JustificationValues.Center },
            new Indentation { FirstLine = "0" },
            new SpacingBetweenLines { Before = "160", After = "40" }),
        new Run(element));
}

static Paragraph CaptionPara(string text) => new Paragraph(
    new ParagraphProperties(
        new Justification { Val = JustificationValues.Center },
        new Indentation { FirstLine = "0" },
        new SpacingBetweenLines { After = "160", Line = "300", LineRule = LineSpacingRuleValues.Auto }),
    new Run(
        new RunProperties(
            new RunFonts { Ascii = "Times New Roman", HighAnsi = "Times New Roman", EastAsia = "宋体" },
            new Bold(),
            new FontSize { Val = "21" }),
        new Text(text)));

static Table StageTable()
{
    string[] headers = { "阶段", "核心能力", "典型任务（以采销为例）" };
    string[][] rows =
    {
        new[] { "Web 1.0", "人获取信息", "检索供应商" },
        new[] { "Web 2.0", "人发布、联系、交易", "发需求、比报价" },
        new[] { "AI应用", "AI理解信息并调用工具", "整理需求、生成询价" },
        new[] { "智能体互联", "跨主体Agent协作", "发现、询价、协商、推进订单" },
    };

    var table = new Table(
        new TableProperties(
            new TableWidth { Width = "5000", Type = TableWidthUnitValues.Pct },
            new TableBorders(
                new TopBorder { Val = BorderValues.Single, Size = 4, Color = "666666" },
                new BottomBorder { Val = BorderValues.Single, Size = 4, Color = "666666" },
                new LeftBorder { Val = BorderValues.Single, Size = 4, Color = "666666" },
                new RightBorder { Val = BorderValues.Single, Size = 4, Color = "666666" },
                new InsideHorizontalBorder { Val = BorderValues.Single, Size = 4, Color = "AAAAAA" },
                new InsideVerticalBorder { Val = BorderValues.Single, Size = 4, Color = "AAAAAA" }),
            new TableLayout { Type = TableLayoutValues.Fixed }),
        new TableGrid(
            new GridColumn { Width = "1400" },
            new GridColumn { Width = "2800" },
            new GridColumn { Width = "4300" }));

    table.Append(TableHeaderRow(headers));
    foreach (var r in rows) table.Append(TableBodyRow(r));
    return table;
}

static TableRow TableHeaderRow(string[] cells)
{
    var row = new TableRow();
    foreach (var c in cells)
    {
        row.Append(new TableCell(
            new TableCellProperties(
                new TableCellWidth { Type = TableWidthUnitValues.Auto },
                new Shading { Val = ShadingPatternValues.Clear, Fill = "E8EEF5" },
                new TableCellVerticalAlignment { Val = TableVerticalAlignmentValues.Center }),
            new Paragraph(
                new ParagraphProperties(
                    new Justification { Val = JustificationValues.Center },
                    new Indentation { FirstLine = "0" },
                    new SpacingBetweenLines { Before = "40", After = "40" }),
                new Run(
                    new RunProperties(
                        new RunFonts { EastAsia = "黑体", Ascii = "Times New Roman", HighAnsi = "Times New Roman" },
                        new Bold(),
                        new FontSize { Val = "21" }),
                    new Text(c)))));
    }
    return row;
}

static TableRow TableBodyRow(string[] cells)
{
    var row = new TableRow();
    for (int i = 0; i < cells.Length; i++)
    {
        row.Append(new TableCell(
            new TableCellProperties(
                new TableCellWidth { Type = TableWidthUnitValues.Auto },
                new TableCellVerticalAlignment { Val = TableVerticalAlignmentValues.Center }),
            new Paragraph(
                new ParagraphProperties(
                    new Justification { Val = i == 0 ? JustificationValues.Center : JustificationValues.Left },
                    new Indentation { FirstLine = "0" },
                    new SpacingBetweenLines { Before = "40", After = "40" }),
                new Run(
                    new RunProperties(
                        new RunFonts { EastAsia = "宋体", Ascii = "Times New Roman", HighAnsi = "Times New Roman" },
                        new FontSize { Val = "21" }),
                    new Text(cells[i]) { Space = SpaceProcessingModeValues.Preserve }))));
    }
    return row;
}

static Run Cite(string n) => new Run(
    new RunProperties(
        new RunFonts { Ascii = "Times New Roman", HighAnsi = "Times New Roman", EastAsia = "宋体" },
        new VerticalTextAlignment { Val = VerticalPositionValues.Superscript },
        new FontSize { Val = "24" }
    ),
    new Text($"[{n}]")
);

static Paragraph BodyPara(params OpenXmlElement[] runs)
{
    var p = new Paragraph(
        new ParagraphProperties(
            new ParagraphStyleId { Val = "Normal" },
            new Justification { Val = JustificationValues.Both },
            new SpacingBetweenLines { Line = "360", LineRule = LineSpacingRuleValues.Auto, After = "120" },
            new Indentation { FirstLine = "480" }
        )
    );
    foreach (var r in runs) p.Append(r);
    return p;
}

static Paragraph FigurePlaceholder(string caption, string hint)
{
    var border = new Paragraph(
        new ParagraphProperties(
            new Justification { Val = JustificationValues.Center },
            new SpacingBetweenLines { Before = "200", After = "60", Line = "360", LineRule = LineSpacingRuleValues.Auto },
            new Indentation { FirstLine = "0" },
            new ParagraphBorders(
                new TopBorder { Val = BorderValues.Single, Size = 4, Color = "808080" },
                new BottomBorder { Val = BorderValues.Single, Size = 4, Color = "808080" },
                new LeftBorder { Val = BorderValues.Single, Size = 4, Color = "808080" },
                new RightBorder { Val = BorderValues.Single, Size = 4, Color = "808080" }
            ),
            new Shading { Val = ShadingPatternValues.Clear, Fill = "F5F5F5" }
        ),
        new Run(
            new RunProperties(
                new RunFonts { EastAsia = "宋体", Ascii = "Times New Roman", HighAnsi = "Times New Roman" },
                new Italic(),
                new Color { Val = "666666" },
                new FontSize { Val = "21" }
            ),
            new Text(hint) { Space = SpaceProcessingModeValues.Preserve }
        )
    );

    // We need two paragraphs: box + caption. Return caption as separate - caller appends both via helper returning array?
    // Simpler: pack as one paragraph with break
    // Actually append both by returning a compound - change approach: return List or use body.Append in caller.
    // For simplicity, make FigurePlaceholder append caption after in one method that returns Paragraph[] - but signature is Paragraph.
    // Use a special marker - change callers to append two elements.
    // Easiest fix: put caption in same bordered para with line break.
    border.AppendChild(new Run(new Break()));
    border.AppendChild(new Run(
        new RunProperties(
            new RunFonts { EastAsia = "宋体", Ascii = "Times New Roman", HighAnsi = "Times New Roman" },
            new Bold(),
            new FontSize { Val = "21" }
        ),
        new Text(caption)
    ));
    return border;
}

static Paragraph RefPara(string text) => new Paragraph(
    new ParagraphProperties(
        new Justification { Val = JustificationValues.Both },
        new SpacingBetweenLines { Line = "300", LineRule = LineSpacingRuleValues.Auto, After = "60" },
        new Indentation { Left = "420", Hanging = "420" }
    ),
    new Run(
        new RunProperties(
            new RunFonts { Ascii = "Times New Roman", HighAnsi = "Times New Roman", EastAsia = "宋体" },
            new FontSize { Val = "21" } // 五号偏小四
        ),
        new Text(text) { Space = SpaceProcessingModeValues.Preserve }
    )
);

static Paragraph NotePara(string text) => new Paragraph(
    new ParagraphProperties(
        new SpacingBetweenLines { Before = "200", Line = "300", LineRule = LineSpacingRuleValues.Auto },
        new Indentation { FirstLine = "0" }
    ),
    new Run(
        new RunProperties(
            new RunFonts { EastAsia = "宋体", Ascii = "Times New Roman", HighAnsi = "Times New Roman" },
            new Color { Val = "666666" },
            new FontSize { Val = "18" }
        ),
        new Text(text) { Space = SpaceProcessingModeValues.Preserve }
    )
);

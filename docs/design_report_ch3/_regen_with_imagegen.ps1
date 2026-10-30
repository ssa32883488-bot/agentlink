# 配置 CUSTOM_IG_API_KEY 后执行本脚本，用 custom-imagegen 重渲六张主题图。
$ErrorActionPreference = "Stop"
$script = "$env:USERPROFILE\.codex\skills\custom-imagegen\scripts\custom_image_gen.py"
$outDir = Join-Path $PSScriptRoot "figures\ai"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

if (-not $env:CUSTOM_IG_API_KEY -and -not $env:MAXOPEN_API_KEY -and -not $env:OPENAI_API_KEY) {
  Write-Error "请先设置环境变量 CUSTOM_IG_API_KEY（或 MAXOPEN_API_KEY），并重启终端/Cursor。"
}

$model = "gpt-image-2"
$base = "https://api.maxopenapi.com/v1"
$size = "1536x1024"

$prompts = @{
  "fig3-1_architecture" = @"
Professional technical architecture diagram for a multi-agent commerce system, clean white background, Chinese labels, layered boxes top to bottom: 1 Human UI and HITL breakpoints, 2 Agent runtimes buyer/supplier/logistics, 3 Business orchestration normal RFQ and group auction, 4 ACPs protocol AIC ACS ADP AIP AMP mTLS, 5 Dual-cloud deploy Tencent and Aliyun, top bar Wutong platform Registry Discovery Kafka, blue green engineering style, no decorative clutter, readable Chinese text
"@
  "fig3-2_framework" = @"
Technical framework diagram, white background, top band open-source ACPs reuse AIC ACS ADP AIP AMP, bottom left normal 10-step procurement path, bottom right group auction with buyer as host, three runtime boxes buyer suppliers logistics, Chinese labels, clean Infographic engineering style
"@
  "fig3-3_seq_normal" = @"
UML-like sequence diagram, white background, lifelines Human Buyer Wutong Suppliers Logistics, 10 numbered steps Chinese labels for procurement RFQ bargain order logistics confirm, blue arrows, clean technical documentation style
"@
  "fig3-4_seq_group" = @"
Sequence diagram group auction, lifelines Human BuyerHost SupplierGroup Logistics, steps conflict suggest, human confirm group, open group, bidding, decide, invite logistics, tickets confirm, Chinese labels, orange accents, white background
"@
  "fig3-5_agent_runtime" = @"
Internal agent runtime architecture boxes: dialog UI, cognition LLM, tool gateway, master data, protocol adapter, ticket ack state, Chinese labels, clean layered software diagram white background
"@
  "fig3-6_deploy" = @"
Dual cloud deployment diagram, left Tencent cloud buyers and logistics, right Aliyun three suppliers, bottom Wutong platform connection, Chinese labels, clean network architecture style white background
"@
}

foreach ($name in $prompts.Keys) {
  $out = Join-Path $outDir "$name.png"
  Write-Host "Generating $name ..."
  py -3 $script generate --prompt $prompts[$name] --model $model --base-url $base --size $size --timeout 300 --out $out
  Write-Host "OK $out"
}
Write-Host "DONE $outDir"

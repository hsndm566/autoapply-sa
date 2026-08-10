# AutoApply SA — n8n Workflows (cloud-backed)

These 66 workflow JSONs are stored in the `hsndm566/autoapply-sa` cloud repo (`cloud-runner` branch) under `/workflows/`.
n8n is retired; these are kept as the canonical cloud copy / backup.

| File | Workflow Name | Nodes | Key Node Types |
|---|---|---|---|
| `0vzVWjrT0PiINdxZ-Brevo_Webhook_Listener.json` | Brevo Webhook Listener | 13 | webhook, if, dataTable, telegram, code |
| `39bV8k08mZPd6KO6-Provider_Health_Check.json` | Provider Health Check | 6 | scheduleTrigger, telegram, code, httpRequest |
| `4XBPY1kpwRD9sg5O-Autopilot.json` | Autopilot | 14 | httpRequest, switch, scheduleTrigger, telegram, code |
| `4hymGz3ZWOYWfhpx-Credential_Importer.json` | Credential Importer | 7 | webhook, splitInBatches, code, httpRequest |
| `5lSlKInKXDDfmHyi-Daily_CSV_Backup.json` | Daily CSV Backup | 7 | dataTable, convertToFile, scheduleTrigger, telegram, readWriteFile |
| `5riTwcPQs5pFMY0l-Site_Translator.json` | Site Translator | 7 | if, form, formTrigger, code, executeWorkflow |
| `5u9IUYirQMB2Jjnb-Polish_hsndm_tech_with_Claude_Opus_one_time_.json` | Polish hsndm.tech with Claude Opus (one-time) | 15 | manualTrigger, noOp, anthropic, stopAndError, if, splitInBatches |
| `6LWSDgkBgiOwiBwy-DT_Probe.json` | DT Probe | 3 | manualTrigger, dataTable |
| `6mnPt3j9qRVw7d8J-Kimi_Delegation_Batch_Send_All_New_Rows_.json` | Kimi Delegation — Batch Send (All New Rows) | 12 | manualTrigger, googleDrive, scheduleTrigger, splitInBatches, dataTable, telegram |
| `760UAWdvJ6gbkPkB-Add_Google_Translate_Widget.json` | Add Google Translate Widget | 5 | manualTrigger, code, github |
| `9xBPxYPpxIEmQdjI-Automated_Job_Applier.json` | Automated Job Applier | 49 | noOp, manualTrigger, formTrigger, httpRequest, if, errorTrigger |
| `AxeeH2LR9asRMjdS-AI_Provider_Hub.json` | AI Provider Hub | 9 | code, executeWorkflowTrigger, httpRequest |
| `AyunO8daMw20yDDJ-Sheets_Tab_Setup_one_shot_.json` | Sheets Tab Setup (one-shot) | 4 | manualTrigger, set, googleSheets |
| `BTVLbgm1dv2NMy7v-Finish_Claude_Opus_drafts_with_my_AI_agents_one_time_.json` | Finish Claude Opus drafts with my AI agents (one-time) | 20 | manualTrigger, noOp, stopAndError, httpRequest, if, splitInBatches |
| `F6PbeH22CEM9obYQ-TG_Live_Confirm.json` | TG Live Confirm | 2 | manualTrigger, telegram |
| `FNDaY5ZxgKtVQww9-AI_Hub_Health.json` | AI Hub & Health | 39 | webhook, httpRequest, if, scheduleTrigger, executeWorkflowTrigger, dataTable |
| `FUL8M9AOLSG0KLFJ-Kimi_Process_One_Row.json` | Kimi — Process One Row | 64 | httpRequest, googleDrive, if, telegram, googleSheets, set |
| `FxnkBYC23EFWCwx3-TEMP_lock_branch_test.json` | TEMP lock branch test | 10 | manualTrigger, noOp, if, set, dataTable, code |
| `LgqmBFOZhMYhlFhB-DeepSeek_API_Test.json` | DeepSeek API Test | 2 | manualTrigger, httpRequest |
| `NBrmJMZmz4dpHUXK-Automated_Job_Applier_AI_Agent_.json` | Automated Job Applier (AI Agent) | 26 | webhook, outputParserStructured, lmChatOpenAi, httpRequest, lmChatGroq, if |
| `NSQJ7rkKIvsxVAJh-Bearer_ID_Probe_one_shot_.json` | Bearer ID Probe (one-shot) | 3 | manualTrigger, httpRequest |
| `Nm9jDYlm58XXmnLt-OpenCode_API_Ask_HTTP_.json` | OpenCode API — Ask (HTTP) | 5 | manualTrigger, set, code, httpRequest |
| `QrmmXkfF8tGMHzgO-TG_Finalize_Confirm.json` | TG Finalize Confirm | 2 | manualTrigger, telegram |
| `RleawumwNKU6s5NR-Z_ai_Token_Test_one_shot_.json` | Z.ai Token Test (one-shot) | 2 | manualTrigger, httpRequest |
| `S5KDs1kBaIerfJl4-Multi_AI_Page_Builder.json` | Multi-AI Page Builder | 7 | manualTrigger, github, httpRequest, code, executeWorkflow |
| `S6VFIp3kVT1tuJyn-Saas.json` | Saas | 0 |  |
| `TtJB1ptXevCxfnDi-Kimi_Process_One_Row_v3_A_B_.json` | Kimi — Process One Row (v3 A+B) | 84 | noOp, httpRequest, googleDrive, if, telegram, googleSheets |
| `UUZWQXmsZuwmj4DG-Saudi_Job_Firehose.json` | Saudi Job Firehose | 10 | manualTrigger, httpRequest, dataTable, scheduleTrigger, code |
| `VdsJuu7mZAX0oGAy-Job_X_Ray.json` | Job X-Ray | 5 | webhook, code, respondToWebhook, httpRequest |
| `Y9ZqdLeh9LaflRHJ-Provider_Ping_Test.json` | Provider Ping Test | 5 | manualTrigger, code, httpRequest |
| `YLmxe4YNSiBolzFc-Kimi_Delegation_Single_Send.json` | Kimi Delegation — Single Send | 44 | manualTrigger, httpRequest, set, merge, dataTable, telegram |
| `ZMx7tPe7DEC1ZSU5-Automated_Job_Scraper.json` | Automated Job Scraper | 16 | webhook, httpRequest, lmChatGroq, dataTable, set, chainLlm |
| `ZdIUetxYk33vaLyS-Telegram_Monitor.json` | Telegram Monitor | 8 | switch, telegramTrigger, dataTable, telegram, code |
| `aVq9f38Hia1IZaRB-TG_Batch_Summary.json` | TG Batch Summary | 2 | manualTrigger, telegram |
| `bRap6AKKAQKmFT2l-AI_Social_Video_Maker.json` | AI Social Video Maker | 14 | webhook, httpRequest, if, dataTable, respondToWebhook, wait |
| `c1c4qo9dT3cufff9-Restyle_hsndm_tech_dashboard_cv_multi_AI_one_time_.json` | Restyle hsndm.tech dashboard & cv (multi-AI, one-time) | 19 | manualTrigger, noOp, stopAndError, httpRequest, if, splitInBatches |
| `cvZaMo3PoNCD6kAN-Kimi_Delegation_Assistant_Chat.json` | Kimi Delegation — Assistant Chat | 4 | chatTrigger, agent, memoryBufferWindow, lmChatGroq |
| `defEZt9d26Uiw77M-AI_Social_Video_Maker.json` | AI Social Video Maker | 23 | webhook, httpRequest, if, dataTable, respondToWebhook, wait |
| `dwunjTZwKiMQnHnd-Client_Pulse.json` | Client Pulse | 4 | scheduleTrigger, telegram, code, dataTable |
| `eDz9kmZ9SaRCbt3s-Kimi_Process_One_Row_with_Review_.json` | Kimi — Process One Row (with Review) | 75 | noOp, httpRequest, googleDrive, if, telegram, set |
| `eUX8895NF5MtIOlK-Website_HTML_QA_Review.json` | Website HTML QA Review | 11 | httpRequest, gmail, form, merge, formTrigger, code |
| `erM3iyABVXTtyO2q-Temp_Telegram_Finalize.json` | Temp Telegram Finalize | 2 | manualTrigger, telegram |
| `eyr2SckhF4qzwjV3-TEMP_Website_Polish_Opus_.json` | TEMP Website Polish (Opus) | 12 | manualTrigger, anthropic, httpRequest, if, merge, code |
| `hamGETVLdSg735zN-Restore_hsndm_tech_broken_pages.json` | Restore hsndm.tech broken pages | 4 | manualTrigger, github, code, httpRequest |
| `jVHc9wkryw6FxSmX-TG_Confirm.json` | TG Confirm | 2 | manualTrigger, telegram |
| `jmJqSuiqUwe2HRTv-Kimi_Weekly_Report_Card.json` | Kimi — Weekly Report Card | 4 | scheduleTrigger, telegram, code, dataTable |
| `kWnRwBlilQGaojoq-Generate_Website_Pages.json` | Generate Website Pages | 13 | webhook, lmChatOpenAi, httpRequest, respondToWebhook, chainLlm, merge |
| `lTd0ou5XvWVyZNYD-the_new_one.json` | the new one | 81 | manualTrigger, noOp, if, stickyNote, lmChatGroq, switch |
| `nqqNUeWw7D3R2rXk-Deploy_Julie_Chatbot.json` | Deploy Julie Chatbot | 5 | webhook, code, respondToWebhook, github |
| `oh1K4XNx2lUk1SB5-TEMP_S3_Endpoint_Test.json` | TEMP S3 Endpoint Test | 3 | manualTrigger, s3, code |
| `opaHWtXdjFW5hPVs-AI_Provider_Hub.json` | AI Provider Hub | 23 | webhook, httpRequest, if, respondToWebhook, splitInBatches, switch |
| `pbNFG4hfZMA2JjVZ-NVIDIA_NIM_Test_temp_.json` | NVIDIA NIM Test (temp) | 4 | manualTrigger, set, code, httpRequest |
| `q0yLGi7K11WIpB4l-Health_Check.json` | Health Check | 11 | if, dataTable, scheduleTrigger, telegram, code |
| `qGFidCrkDUYCGJXn-Deep_Research.json` | Deep Research | 8 | manualTrigger, stickyNote, httpRequest, sendInBlue, set, telegram |
| `qX7yq9tAhy1WMZ87-Job_Submission_Form.json` | Job Submission Form | 2 | dataTable, formTrigger |
| `rLFw7OE8vADaQrIY-Applier_DRY_RUN_temp_.json` | Applier DRY-RUN (temp) | 14 | manualTrigger, outputParserStructured, lmChatOpenAi, httpRequest, lmChatGroq, set |
| `rP30O29gtE25tUcz-TEMP_add_job_branch_test.json` | TEMP add-job branch test | 4 | manualTrigger, dataTable, set, code |
| `ruWrLnz5TVYoJRwz-AI_Website_Builder.json` | AI Website Builder | 48 | manualTrigger, webhook, github, httpRequest, if, respondToWebhook |
| `sAUjvzAPSyjlqmdM-job_applier_backup.json` | job applier backup | 26 | webhook, outputParserStructured, lmChatOpenAi, httpRequest, lmChatGroq, if |
| `skvWlvwlL0sPIvSv-the_new_one_Error_Handler.json` | the new one - Error Handler | 7 | httpRequest, dataTable, telegram, errorTrigger, code |
| `uRnZZS2MwD3oYs3H-Applier_DRY_RUN_v2_temp_.json` | Applier DRY-RUN v2 (temp) | 14 | manualTrigger, outputParserStructured, lmChatOpenAi, httpRequest, lmChatGroq, set |
| `vxcjNiSawqZd2vrw-Continue_hsndm_tech_from_Opus_drafts_multi_AI_one_time_.json` | Continue hsndm.tech from Opus drafts (multi-AI, one-time) | 24 | manualTrigger, noOp, stopAndError, httpRequest, if, splitInBatches |
| `ww8z9S83iB1110Ix-Provider_Test_temp_.json` | Provider Test (temp) | 4 | manualTrigger, httpRequest |
| `zN3AFLNvhPzVQ5eW-TG_Self_Test_Report.json` | TG Self Test Report | 2 | manualTrigger, telegram |
| `zN6y0EneCaQyQwci-Job_Applier_Error_Alerts.json` | Job Applier — Error Alerts | 3 | gmail, errorTrigger, code |
| `zm0EXNfiARXgHz8x-AI_Call_resilient_.json` | AI Call (resilient) | 9 | set, code, executeWorkflowTrigger, httpRequest |

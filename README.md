# 台股觀測站 V2.0 — GitHub 免費雲端版

使用公開 GitHub repository、標準 Actions runner 與 GitHub Pages。無須家用電腦常駐、Python 安裝或付費 API 金鑰。網站與程式碼公開，請勿上傳個人資料、券商帳戶、密碼。排程不是即時保證。

## 第一次部署（Windows / GitHub 網頁與 GitHub Desktop）
1. 登入 https://github.com/new ，Repository name 輸入 `taiwan-market-app`，選 Public，勾 Add a README file，建立。
2. 安裝並登入 https://desktop.github.com/ 。File → Clone repository，選剛剛建立的 repo，Clone。Repository → Show in Explorer 開啟本機資料夾。
3. 解壓縮本專案，把 ZIP 內的 `.github`、`scripts`、`site`、`README.md` 複製進剛才的資料夾（覆蓋初始 README）。不要多包一層；`.github` 必須存在。
4. GitHub Desktop 左下 Summary 填 `Initial market dashboard`，Commit to main，Push origin。
5. 回 GitHub 網站的專案 Settings → Pages → Build and deployment → Source 選 GitHub Actions。Settings → Actions → General 若需要，允許 Actions 並確認 Workflow permissions 可寫入；若組織政策禁止，需由管理員調整。
6. Actions → 台股每日更新與網站部署 → Run workflow → Branch main → Run workflow。初次可勾 `full` 補齊歷史；亦可先不勾、之後再補齊。等待 Actions 顯示綠色，回 Settings → Pages 查看 Visit site 網址。若上傳時 push 首次部署失敗（尚未開啟 Pages），設定好後重跑即可。
7. 以 iPhone Safari 開啟網址 `https://你的GitHub帳號.github.io/taiwan-market-app/`，分享 → 加入主畫面（若有「以網頁 App 開啟」，請打開）→ 新增。

## 日常操作
- 每週一至五台灣時間 22:17，翌日 01:43 補抓一次（Actions 排程可能延遲或未觸發）。公休日沒有新資料就保留原資料。
- 手機「重新整理」只重新讀網址上的資料；需強制抓資料時使用 GitHub Actions → Run workflow。
- 初次內建 45 筆先前整理的週資料（舊來源口徑未重新驗證）；日資料由 Actions 首次抓取，沒有數值不填造。日 K 自 2026/01/01，均線需足夠日數才顯示。日線及融資維持率估算與舊週資料口徑可能不同。最近三個交易日每次重抓，過往缺值分批補抓，每次 8 日（全量手動模式最多 240 日）。
- GitHub Actions 以 JSON/CSV 保存日資料並部署網站；手機無網路時，若已成功造訪並快取，可讀最後一次資料並顯示離線提示。
- 免費公開 repo 的排程可能在 60 天沒有 repo 活動後停用；若未更新，查看 Actions、重新啟用並手動執行。請勿上傳私密資料。

## 資料與限制
- TWSE MI_5MINS_HIST（日 OHLC）、FMTQIK（成交金額、成交股數、收盤指數交叉檢查）、MI_MARGN（融資餘額）、MI_INDEX（收盤價）。
- 「上市融資維持率」是以上市個股融資交易單位 × 收盤價的合計／市場融資金額（仟元）×100 的市場估算。個股缺當日收盤時，僅在近五個有資料的交易日中使用前收並標註；仍缺資料則留空。不是券商個人維持率、不是官方發布的整戶維持率，也不是單獨買賣依據。
- 外部 API 可能限流、改欄位、阻擋 GitHub 雲端 IP；實際連線尚未端到端驗證。抓取異常顯示於更新紀錄，已儲存資料保留。請檢查長期未更新的日期或缺值。
- 免費架構沒有私有登入、推播、逐秒股價；如需擴充另行評估。

## 檔案
- `.github/workflows/market.yml`：排程和 Pages 部署
- `scripts/update.py`：Python 資料整理（標準函式庫）
- `site/`：響應式前端 + PWA + JSON/CSV

"""
reporters/styles.py
───────────────────
All CSS for the Support Dashboard.
Imported by reporters/cw_report.py via _css().
"""
from __future__ import annotations


def _css() -> str:
    return """
:root{
  /* Dark theme — deep navy, vivid accents */
  --bg:#0b1120;--sf:#131d30;--sf2:#1a2742;--bd:#253555;
  --tx:#e8f1ff;--mt:#7a9fc8;--muted:var(--mt);
  --ac:#4da6ff;--acdim:rgba(77,166,255,.18);
  --sev-fatal:#c084fc;--sev-crit:#ff5a5a;--sev-err:#ff5a5a;
  --sev-exc:#ff9050;--sev-warn:#fcd34d;--sev-ok:#4ade80;
  --accent:var(--ac);
  --r:8px;--sh:0 2px 8px rgba(0,0,0,.5);
  --hdr-grad:linear-gradient(135deg,#131d30 0%,#0f1a2e 100%);
}
@media(prefers-color-scheme:light){
  :root:not([data-theme="dark"]){
    --bg:#eef4ff;--sf:#ffffff;--sf2:#dbeafe;--bd:#93c5fd;
    --tx:#0f2850;--mt:#3b6fa0;
    --ac:#1a6ef5;--acdim:rgba(26,110,245,.13);
    --sev-fatal:#7c3aed;--sev-crit:#dc2020;--sev-err:#dc2020;
    --sev-exc:#d4600a;--sev-warn:#b45309;--sev-ok:#157a38;
    --sh:0 1px 4px rgba(15,40,80,.12);
    --hdr-grad:linear-gradient(135deg,#ffffff 0%,#f0f8ff 100%);
  }
}
:root[data-theme="light"]{
  --bg:#eef4ff;--sf:#ffffff;--sf2:#dbeafe;--bd:#93c5fd;
  --tx:#0f2850;--mt:#3b6fa0;
  --ac:#1a6ef5;--acdim:rgba(26,110,245,.13);
  --sev-fatal:#7c3aed;--sev-crit:#dc2020;--sev-err:#dc2020;
  --sev-exc:#d4600a;--sev-warn:#b45309;--sev-ok:#157a38;
  --sh:0 1px 4px rgba(15,40,80,.12);
  --hdr-grad:linear-gradient(135deg,#ffffff 0%,#f0f8ff 100%);
}
:root[data-theme="dark"]{
  --bg:#0b1120;--sf:#131d30;--sf2:#1a2742;--bd:#253555;
  --tx:#e8f1ff;--mt:#7a9fc8;
  --ac:#4da6ff;--acdim:rgba(77,166,255,.18);
  --sev-fatal:#c084fc;--sev-crit:#ff5a5a;--sev-err:#ff5a5a;
  --sev-exc:#ff9050;--sev-warn:#fcd34d;--sev-ok:#4ade80;
  --sh:0 2px 8px rgba(0,0,0,.5);
  --hdr-grad:linear-gradient(135deg,#131d30 0%,#0f1a2e 100%);
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',system-ui,sans-serif;background:var(--bg);
     color:var(--tx);font-size:14px;line-height:1.6;min-height:100vh}
a{color:var(--ac)}
.key-link{font-family:'JetBrains Mono',monospace;font-size:12px;
          font-weight:600;color:var(--ac);text-decoration:none}
.key-link:hover{text-decoration:underline}
header{position:sticky;top:0;z-index:100;background:var(--hdr-grad);
       border-bottom:2px solid var(--ac);box-shadow:var(--sh)}
.hi{max-width:1420px;margin:0 auto;display:flex;align-items:center;
    gap:20px;padding:0 24px;height:54px}
.brand{display:flex;align-items:center;gap:8px;flex-shrink:0}
.bi{font-size:17px}
.bn{font-weight:700;font-size:14px;letter-spacing:-.02em}
.bs{color:var(--mt);font-size:11px;font-weight:500;
    border-left:1px solid var(--bd);padding-left:8px;margin-left:2px}
.mtabs{display:flex;gap:4px;flex:1;justify-content:center}
.mtab{display:flex;align-items:center;gap:6px;padding:5px 16px;
      border-radius:6px;border:1px solid transparent;cursor:pointer;
      font-family:'Inter',sans-serif;font-size:13px;font-weight:500;
      background:transparent;color:var(--mt);transition:all .15s}
.mtab:hover{background:var(--acdim);color:var(--ac);border-color:var(--ac)}
.mtab.active{background:var(--ac);color:#fff;border-color:var(--ac);
             box-shadow:0 0 12px var(--acdim)}
.tab-count{font-size:11px;font-weight:700;padding:1px 6px;
           border-radius:10px;background:var(--sev-err);color:#fff;
           font-variant-numeric:tabular-nums;min-width:18px;text-align:center}
.hmeta{font-size:12px;color:var(--mt);flex-shrink:0;
       display:flex;gap:8px;align-items:center}
.dot{color:var(--bd)}
.ts-block{display:flex;flex-direction:column;align-items:flex-end;line-height:1.25}
.ts-label{font-size:10px;font-weight:600;text-transform:uppercase;
          letter-spacing:.07em;color:var(--mt)}
.ts-value{font-family:'JetBrains Mono',monospace;font-size:12px;
          font-weight:500;color:var(--tx);white-space:nowrap}
main{min-height:calc(100vh - 54px - 44px)}
.container{max-width:1420px;margin:0 auto;padding:24px 24px 48px}
.tpanel{display:none}.tpanel.active{display:block}
.stats-grid{display:grid;grid-template-columns:repeat(4,1fr);
            gap:14px;margin-bottom:22px}
@media(max-width:1100px){.stats-grid{grid-template-columns:repeat(3,1fr)}}
@media(max-width:720px){.stats-grid{grid-template-columns:repeat(2,1fr)}}
.stat-card{background:var(--sf);border:1px solid var(--bd);
           border-radius:var(--r);padding:16px 20px;
           border-top:3px solid var(--ac);transition:box-shadow .15s}
.stat-card:hover{box-shadow:0 4px 16px var(--acdim)}
.stat-val{font-size:28px;font-weight:800;letter-spacing:-.03em;
          font-variant-numeric:tabular-nums;line-height:1;margin-bottom:6px}
.stat-lbl{font-size:11px;color:var(--mt);font-weight:600;
          text-transform:uppercase;letter-spacing:.07em}
.card{background:var(--sf);border:1px solid var(--bd);
      border-radius:var(--r);margin-bottom:18px;
      box-shadow:var(--sh);overflow:hidden;transition:border-color .15s}
.card:hover{border-color:var(--ac)}
.card-hd{display:flex;align-items:center;gap:10px;
         padding:13px 20px;border-bottom:1px solid var(--bd);
         background:var(--sf2)}
.card-hd h2,.card-hd h3{font-size:13px;font-weight:700;flex:1}
.chip{font-size:11px;font-weight:500;padding:2px 8px;
      border-radius:20px;background:var(--sf2);
      color:var(--mt);border:1px solid var(--bd);white-space:nowrap}
.tw{overflow-x:auto}
.dt{width:100%;border-collapse:collapse;font-size:13px}
.dt th{padding:7px 12px;text-align:left;font-size:10px;font-weight:700;
       text-transform:uppercase;letter-spacing:.08em;color:var(--mt);
       background:var(--sf2);border-bottom:1px solid var(--bd);white-space:nowrap}
.dt td{padding:8px 12px;border-bottom:1px solid var(--bd);vertical-align:middle}
.dt tr:last-child td{border-bottom:none}
.dt tr:hover td{background:var(--sf2)}
.row-fatal td{background:rgba(192,132,252,.13)}
.row-crit td{background:rgba(255,90,90,.13)}
.row-error td{background:rgba(255,90,90,.08)}
.row-warn td{background:rgba(252,211,77,.09)}
.row-fatal:hover td{background:rgba(192,132,252,.22)!important}
.row-crit:hover td{background:rgba(255,90,90,.22)!important}
.row-error:hover td{background:rgba(255,90,90,.15)!important}
.row-warn:hover td{background:rgba(252,211,77,.16)!important}
.rank{color:var(--mt);font-size:11px;width:28px;font-variant-numeric:tabular-nums}
.num{font-weight:600;font-variant-numeric:tabular-nums;white-space:nowrap;
     text-align:right;width:60px}
.ts{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--mt);white-space:nowrap;min-width:148px}
.mono{font-family:'JetBrains Mono',monospace;font-size:12px;word-break:break-all}
.sm{font-size:11px}.text-m{color:var(--mt)}
.dt td{word-wrap:break-word;overflow-wrap:break-word;max-width:300px}
.expand-cell{max-width:340px;white-space:normal;word-break:break-word;
             overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;
             -webkit-box-orient:vertical;cursor:pointer}
.expand-cell:hover{color:var(--ac)}
.expand-cell.expanded{-webkit-line-clamp:unset;display:block;max-width:520px}
.msg-cell{max-width:480px;white-space:normal;word-break:break-word}
.sev-badge{display:inline-block;font-size:10px;font-weight:700;
           padding:2px 6px;border-radius:4px;color:#fff;
           letter-spacing:.04em;white-space:nowrap}
.jstatus-badge{display:inline-block;font-size:11px;font-weight:600;
               padding:2px 8px;border-radius:4px;border:1px solid;white-space:nowrap}
/* Category breakdown panel */
.cat-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));
          gap:12px;padding:16px 20px}
.cat-card{background:var(--bg);border:1px solid var(--bd);border-radius:8px;
          padding:12px 14px}
.cat-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.cat-name{font-size:12px;font-weight:600}
.cat-count{font-size:18px;font-weight:700;color:var(--tx)}
.cat-bar-bg{height:4px;background:var(--sf2);border-radius:2px;overflow:hidden;margin-bottom:5px}
.cat-bar{height:4px;border-radius:2px}
.cat-pct{font-size:10px;color:var(--mt)}
/* Per-row category chip */
.cat-chip{display:inline-block;font-size:10px;font-weight:600;
          padding:2px 7px;border-radius:20px;border:1px solid;white-space:nowrap}
.bar-track{background:var(--sf2);border-radius:4px;overflow:hidden;
           min-width:50px;flex:1}
.bar-fill{border-radius:4px;transition:width .3s ease}
.etab-strip{display:flex;gap:6px;margin-bottom:18px;flex-wrap:wrap}
.etab{padding:6px 18px;border-radius:20px;border:1px solid var(--bd);
      background:var(--sf);color:var(--mt);cursor:pointer;
      font-family:'Inter',sans-serif;font-size:13px;font-weight:500;
      transition:all .15s}
.etab:hover{border-color:var(--ac);color:var(--ac)}
.etab.active{background:var(--ac);border-color:var(--ac);color:#fff;
             box-shadow:0 2px 10px var(--acdim);font-weight:700}
.epanel{display:none}.epanel.active{display:block}
.env-grid{display:grid;grid-template-columns:1fr 300px;gap:16px}
@media(max-width:960px){.env-grid{grid-template-columns:1fr}}
.span-main{min-width:0}
.side-col{display:flex;flex-direction:column;gap:16px}
.svc-bars{padding:12px 16px 14px;display:flex;flex-direction:column;gap:10px}
.svc-row{display:flex;align-items:center;gap:8px}
.svc-nm{font-size:12px;font-weight:500;width:120px;flex-shrink:0;
        white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.svc-n{font-size:11px;color:var(--mt);width:44px;text-align:right;
       flex-shrink:0;font-variant-numeric:tabular-nums}
.sev-bars{padding:12px 16px 14px;display:flex;flex-direction:column;gap:8px}
.sev-row{display:flex;align-items:center;gap:8px}
.sev-n{font-size:11px;font-variant-numeric:tabular-nums;
       color:var(--mt);width:40px;text-align:right;flex-shrink:0}
.json-cell{max-width:380px;cursor:pointer;vertical-align:top}
.json-cell pre{font-family:'JetBrains Mono',monospace;font-size:11px;
               white-space:pre-wrap;word-break:break-all;color:var(--mt);
               max-height:44px;overflow:hidden;line-height:1.5}
.json-cell:hover pre{color:var(--ac)}
.json-cell.expanded pre{max-height:none}
.empty-state{padding:48px 24px;text-align:center;color:var(--mt)}
.empty-state .ei{font-size:30px;margin-bottom:10px}
.empty-state .hint{font-size:12px;margin-top:6px}
.sync-header{display:flex;align-items:center;gap:10px;margin-bottom:16px;
             flex-wrap:wrap}
.rds-info{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:16px}
.sync-badge{font-size:11px;font-weight:700;padding:3px 10px;border-radius:12px;
            background:var(--acdim);border:1px solid var(--ac);color:var(--ac);
            white-space:nowrap;letter-spacing:.02em}
.sync-note{font-size:11px;color:var(--mt)}
/* Infra age badges */
.age-badge{display:inline-block;font-size:10px;font-weight:600;
           padding:2px 7px;border-radius:20px;border:1px solid;white-space:nowrap}
.age-unk{color:var(--mt);border-color:var(--bd);background:var(--sf2)}
.footer{text-align:center;color:var(--mt);font-size:11px;
        padding:14px;border-top:1px solid var(--bd)}
"""

"""
PAWGRESS — Performance Gamification Dashboard
Streamlit · Google Sheets Backend  v2.4 | Season April
Service Account : daily-tracker@dailytracker-490806.iam.gserviceaccount.com
Spreadsheet ID  : 14J8ptb6YIkBAJXLpNSpFPC_EtT3H24Mcyo2UPHmSMcw

BUG FIXES v2.4.1:
  ✅ FIX: Workbook di-cache dengan @st.cache_resource → koneksi sekali, reuse
  ✅ FIX: Semua update cell digabung jadi 1 batch_update → dari 9 calls → 1 call
  ✅ FIX: get_all_rows pakai workbook cached, bukan koneksi baru
  ✅ FIX: DataFrame.get("Status") → df["Status"] (DataFrame tidak punya .get)
  ✅ FIX: sheets_ready di-reset saat logout
  ✅ FIX: load_data tidak lagi memanggil init_all_sheets (cegah loop)
  ✅ FIX: QC form submit button dibaca dengan benar
  ✅ FIX: inp_w unused variable dihapus
  ✅ FIX: row.get("Date", TODAY) minor fix
  ✅ FIX: st.rerun() selalu dilanjutkan return
"""

import streamlit as st
import pandas as pd
import gspread
import pytz
import uuid
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials

# ══════════════════════════════════════════════════════════
#  PAGE CONFIG
# ══════════════════════════════════════════════════════════
st.set_page_config(
    page_title="PAWGRESS · Performance Dashboard",
    page_icon="🐾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════════════
SHEET_ID    = "14J8ptb6YIkBAJXLpNSpFPC_EtT3H24Mcyo2UPHmSMcw"
SECRETS_KEY = "gcp_service_account"
TZ_JKT      = pytz.timezone("Asia/Jakarta")

ALL_STAFF = {
    "Manager": ["Manager"],
    "Finance": sorted(["Fandi", "Yati", "Riega"]),
    "Booker":  sorted(["Vial", "Vero", "Geraldi", "Farras", "Baldy",
                        "Meiji", "Rida", "Ade", "Selvy", "Firda"]),
}
ALL_STAFF_FLAT = ["Manager"] + ALL_STAFF["Finance"] + ALL_STAFF["Booker"]
STAFF_ROLE_MAP = {s: r for r, members in ALL_STAFF.items() for s in members}
STAFF_COLORS   = {
    "Vial":"var(--sb)","Fandi":"#3a87ab","Geraldi":"#4d9c38","Yati":"#b8940a",
    "Meiji":"#534AB7","Farras":"#c52330","Riega":"#0F6E56","Vero":"#993556",
    "Rida":"#C9952A","Ade":"#378ADD","Selvy":"#51a1c4","Baldy":"#8B6914",
    "Firda":"#6B7280","Manager":"var(--sb)",
}
PASSWORDS = {
    "Manager":"789789","Fandi":"fandi123","Yati":"yati123","Riega":"riega123",
    "Vial":"vial123","Vero":"vero123","Geraldi":"geraldi123","Farras":"farras123",
    "Baldy":"baldy123","Meiji":"meiji123","Rida":"rida123","Ade":"ade123",
    "Selvy":"selvy123","Firda":"firda123",
}
SLA_CONFIG = {
    "Cek Harga Hotel":      {"ideal":5,  "maks":10, "xp":5,  "cat":"Fast Response","prefix":"CHK"},
    "Booking Hotel":        {"ideal":10, "maks":20, "xp":10, "cat":"Standard",     "prefix":"BK"},
    "Booking Urgent":       {"ideal":25, "maks":40, "xp":25, "cat":"Priority",     "prefix":"BKU"},
    "Revisi Booking":       {"ideal":10, "maks":20, "xp":10, "cat":"Standard",     "prefix":"RVS"},
    "Pengajuan Pembayaran": {"ideal":15, "maks":30, "xp":15, "cat":"Medium",       "prefix":"PBY"},
    "Follow Up TP/TR/PO":   {"ideal":5,  "maks":15, "xp":5,  "cat":"Fast Response","prefix":"FTP"},
    "Follow Up Payment":    {"ideal":5,  "maks":15, "xp":5,  "cat":"Fast Response","prefix":"FPY"},
    "Inject DTM":           {"ideal":5,  "maks":10, "xp":5,  "cat":"Fast Response","prefix":"DTM"},
    "Rekap Tagihan":        {"ideal":20, "maks":60, "xp":20, "cat":"Heavy Task",   "prefix":"RKP"},
    "Refund":               {"ideal":10, "maks":30, "xp":10, "cat":"Medium",       "prefix":"RFD"},
    "Void":                 {"ideal":5,  "maks":10, "xp":5,  "cat":"Fast Response","prefix":"VD"},
    "Reconfirmed":          {"ideal":15, "maks":30, "xp":15, "cat":"Medium",       "prefix":"RCF"},
}
TASK_TYPE_LIST  = list(SLA_CONFIG.keys())
PENALTY_TYPES   = {
    "Kesalahan Input Data":-10,"Revisi Berulang":-5,"Keterlambatan Input":-5,
    "Void Akibat Kelalaian":-25,"Komplain Tamu":-35,"Data Tidak Lengkap":-5,
}
STATUS_LIST = ["In Progress","Pending","Waiting Confirmation","Done","On Hold","Cancelled"]
LEVELS = [
    (0,"🐾 Kitten"),(100,"🐱 Kucing Kampung"),(300,"🐈 Oyen"),
    (600,"🐈 Kucing Garong"),(1000,"🐆 Kucing Elite"),
    (1800,"🐅 Kucing Sultan"),(3000,"👑 King of Paw"),
]

# ── Sheet Headers ─────────────────────────────────────────
# KOLOM (1-based): A=Date B=Staff C=Role D=TaskType E=BookingID F=Hotel
#                  G=Client H=Notes I=Status J=SLAMinutes K=XP L=Coin
#                  M=QCStatus N=QCBy O=QCNotes P=RefID Q=Timestamp R=TimestampEdit
TASK_HEADERS    = ["Date","Staff","Role","Task Type","Booking ID","Hotel","Client",
                   "Notes","Status","SLA Minutes","XP","Coin","QC Status","QC By",
                   "QC Notes","Ref ID","Timestamp","Timestamp Edit"]
QC_HEADERS      = ["Date","QC By","QC Role","Target Staff","Ref ID","Task Type",
                   "QC Status","QC Notes","XP Awarded","Timestamp"]
SESSION_HEADERS = ["Date","Staff","Role","Login Time","Logout Time","Duration Minutes","Status"]
PROJECT_HEADERS = ["Project ID","Name","Category","Deadline","Staff","Target XP",
                   "Progress","Status","Created"]
XP_LOG_HEADERS  = ["Timestamp","Staff","Type","Amount","Reason","Applied By"]

# ── Weekend & Holiday Bonus ────────────────────────────
HOLIDAY_BONUS = {
    "saturday": {"xp":15,"coin":5, "label":"Sabtu",        "color":"#3a87ab"},
    "sunday":   {"xp":20,"coin":8, "label":"Minggu",       "color":"#d97706"},
    "holiday":  {"xp":25,"coin":10,"label":"Tanggal Merah","color":"#dc2626"},
}
HOLIDAYS_2026 = {
    "2026-01-01","2026-01-27","2026-01-28","2026-01-29","2026-01-30",
    "2026-02-18","2026-03-20","2026-03-28","2026-03-30","2026-03-31",
    "2026-04-01","2026-04-02","2026-04-03","2026-05-01","2026-05-14",
    "2026-05-24","2026-05-29","2026-06-01","2026-06-10","2026-07-16",
    "2026-08-17","2026-08-20","2026-09-10","2026-09-11","2026-10-01",
    "2026-11-11","2026-12-24","2026-12-25",
}

# ── Column index map (0-based untuk pandas, 1-based untuk gspread) ──
COL = {h: i+1 for i, h in enumerate(TASK_HEADERS)}  # gspread 1-based
# COL["Date"]=1, COL["Staff"]=2, ..., COL["Ref ID"]=16, ...

# ══════════════════════════════════════════════════════════
#  CSS
# ══════════════════════════════════════════════════════════
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;500;600;700&family=DM+Mono:wght@400;500&display=swap');

/* ── Design Tokens ── */
:root{
  --blue:#51a1c4;    --blue2:#3a87ab;   --bluel:#daedf5;   --bluell:#edf6fa;
  --rose:#b13f54;    --rose2:#8c3244;   --rosel:#f5dde1;   --rosell:#fbf0f2;
  --gold:#ddb551;    --gold2:#b89238;   --goldl:#f8edcf;   --goldll:#fdf6e7;
  --stone:#706948;   --stone2:#5a5439;  --stonel:#e8e3d8;  --stonell:#f4f2ec;
  --ash:#e8eaea;     --ash2:#d0d3d3;    --ash3:#b2b6b6;    --ash4:#6b7070;
  --bg:#f4f7f8;      --bg2:#ecf0f1;
  --ink:#1a2729;     --ink2:#2d3f42;    --ink3:#4a5e61;    --ink4:#7a9094;
  --line:rgba(81,161,196,.14);
  --line2:rgba(81,161,196,.07);
  --sb:#1c2e35;
  --font:'Sora',sans-serif;
  --mono:'DM Mono',monospace;
  --r:8px; --rl:12px;
}

/* ── Base ── */
html,body,[class*="css"]{font-family:var(--font)!important;background:var(--bg)!important;color:var(--ink)!important;}
.stApp{background:var(--bg)!important;}
#MainMenu,footer,header{visibility:hidden;}
.block-container{padding-top:.6rem!important;padding-bottom:1.5rem!important;max-width:1240px!important;}

/* ── Sidebar shell ── */
section[data-testid="stSidebar"]{background:var(--sb)!important;border-right:none!important;}
section[data-testid="stSidebar"] *{color:rgba(255,255,255,.7)!important;}
section[data-testid="stSidebar"] hr{border-color:rgba(255,255,255,.07)!important;margin:3px 0!important;}
section[data-testid="stSidebar"] > div:first-child{padding:0!important;margin:0!important;}
section[data-testid="stSidebar"] .block-container{padding:0!important;margin:0!important;}
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{gap:0!important;padding:0!important;margin:0!important;}
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div{padding:0!important;margin:0!important;width:100%!important;}
section[data-testid="stSidebar"] .element-container{padding:0!important;margin:0!important;width:100%!important;}
section[data-testid="stSidebar"] .stButton{padding:0!important;margin:0!important;width:100%!important;}
section[data-testid="stSidebar"] .stButton > div{padding:0!important;margin:0!important;width:100%!important;}

/* ── Sidebar nav button ── */
section[data-testid="stSidebar"] .stButton > button{
  font-family:var(--font)!important;
  font-size:13px!important;
  font-weight:400!important;
  color:rgba(255,255,255,.5)!important;
  background:transparent!important;
  border:1px solid transparent!important;
  border-radius:8px!important;
  width:calc(100% - 16px)!important;
  margin:1px 8px!important;
  padding:9px 13px!important;
  text-align:left!important;
  justify-content:flex-start!important;
  display:flex!important;
  align-items:center!important;
  gap:8px!important;
  cursor:pointer!important;
  transition:all .1s!important;
  line-height:1.3!important;
  box-sizing:border-box!important;
  min-height:unset!important;
  height:auto!important;
}
section[data-testid="stSidebar"] .stButton > button p{
  font-size:13px!important;font-weight:400!important;line-height:1.3!important;margin:0!important;
}
section[data-testid="stSidebar"] .stButton > button:hover{
  background:rgba(255,255,255,.07)!important;color:rgba(255,255,255,.88)!important;
}
section[data-testid="stSidebar"] .stButton > button[kind="primary"]{
  color:#fff!important;font-weight:600!important;
  background:rgba(81,161,196,.22)!important;
  border:1px solid rgba(81,161,196,.38)!important;
}
section[data-testid="stSidebar"] .stButton > button[kind="primary"] p{
  font-weight:600!important;color:#fff!important;
}
section[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover{
  background:rgba(81,161,196,.3)!important;
}

/* ── Form elements ── */
.stButton > button{font-family:var(--font)!important;font-weight:500!important;border-radius:var(--r)!important;transition:all .1s!important;}
.stTextInput > div > div > input,.stSelectbox > div > div,.stTextArea textarea,.stNumberInput input{
  font-family:var(--font)!important;font-size:13px!important;
  border-radius:var(--r)!important;
  border:1.5px solid var(--line)!important;
  background:#fff!important;color:var(--ink)!important;
}
hr{border-color:var(--line)!important;}
.stSuccess{background:var(--bluel)!important;color:var(--blue2)!important;border:1px solid rgba(81,161,196,.3)!important;border-radius:var(--r)!important;font-size:13px!important;}
.stWarning{background:var(--goldl)!important;color:var(--gold2)!important;border:1px solid rgba(221,181,81,.3)!important;border-radius:var(--r)!important;font-size:13px!important;}
.stError{background:var(--rosel)!important;color:var(--rose2)!important;border:1px solid rgba(177,63,84,.3)!important;border-radius:var(--r)!important;font-size:13px!important;}
.stInfo{background:var(--bluell)!important;color:var(--blue2)!important;border:1px solid rgba(81,161,196,.25)!important;border-radius:var(--r)!important;font-size:13px!important;}
.stTabs [data-baseweb="tab-list"]{gap:0!important;border-bottom:1px solid var(--line)!important;}
.stTabs [data-baseweb="tab"]{font-family:var(--font)!important;font-size:13px!important;font-weight:400!important;color:var(--ink4)!important;padding:8px 14px!important;}
.stTabs [aria-selected="true"]{color:var(--blue)!important;font-weight:600!important;border-bottom:2px solid var(--blue)!important;}

/* ── Cards ── */
.card{background:#fff;border:1px solid var(--line);border-radius:var(--rl);padding:14px 16px;margin-bottom:10px;}
.card-hd{font-size:12px;font-weight:600;color:var(--ink);margin-bottom:12px;display:flex;justify-content:space-between;align-items:center;}
.card-hd span{font-size:11px;font-weight:400;color:var(--ink4);}

/* ── Stat strip ── */
.stat-row{display:grid;gap:1px;background:var(--line);border:1px solid var(--line);border-radius:var(--rl);overflow:hidden;margin-bottom:14px;}
.stat-row-4{grid-template-columns:repeat(4,1fr);}
.stat-row-3{grid-template-columns:repeat(3,1fr);}
.stat-cell{background:#fff;padding:12px 14px;}
.stat-num{font-size:22px;font-weight:600;font-family:var(--mono);letter-spacing:-.4px;line-height:1;color:var(--ink);}
.stat-lbl{font-size:10px;color:var(--ink4);margin-top:3px;text-transform:uppercase;letter-spacing:.3px;}
.stat-sub{font-size:11px;margin-top:2px;}

/* ── Pills ── */
.pill{display:inline-flex;align-items:center;font-size:10px;font-weight:600;padding:2px 8px;border-radius:99px;white-space:nowrap;}
.pill-done{background:var(--bluel);color:var(--blue2);}
.pill-prog{background:var(--goldl);color:var(--gold2);}
.pill-pend{background:var(--stonel);color:var(--stone2);}
.pill-err{background:var(--rosel);color:var(--rose2);}
.pill-gray{background:var(--bg2);color:var(--ink4);}
/* legacy aliases */
.pill-green{background:var(--bluel);color:var(--blue2);}
.pill-blue{background:var(--bluell);color:var(--blue2);}
.pill-amber{background:var(--goldl);color:var(--gold2);}
.pill-red{background:var(--rosel);color:var(--rose2);}
.pill-navy{background:var(--stonel);color:var(--stone2);}

/* ── Mono tag (ref id) ── */
.mtag{font-family:var(--mono);font-size:10px;padding:1px 6px;border-radius:3px;background:var(--bluell);color:var(--blue2);}

/* ── Row cards ── */
.row-card{background:#fff;border:1px solid var(--line);border-radius:var(--r);padding:11px 14px;margin-bottom:6px;transition:border-color .1s;}
.row-card:hover{border-color:var(--blue);}
.task-title{font-size:13px;font-weight:600;color:var(--ink);}
.task-meta{font-size:11px;color:var(--ink4);margin-top:3px;display:flex;gap:6px;align-items:center;flex-wrap:wrap;}

/* ── SLA ── */
.sla-ok{color:var(--blue2);font-size:11px;font-weight:600;}
.sla-w{color:var(--gold2);font-size:11px;font-weight:600;}
.sla-ov{color:var(--rose);font-size:11px;font-weight:600;}
.sla-d{color:var(--ink4);font-size:11px;}

/* ── Progress bar ── */
.pbar{height:3px;background:var(--bg2);border-radius:99px;overflow:hidden;}
.pbar-fill{height:100%;border-radius:99px;}

/* ── XP panel ── */
.xp-panel{background:var(--sb);border-radius:var(--r);padding:14px 16px;}
.xp-lbl{font-size:11px;color:rgba(255,255,255,.4);font-weight:500;}
.xp-val{font-family:var(--mono);font-size:11px;font-weight:600;}
.xp-line{display:flex;justify-content:space-between;padding:2px 0;}
.xp-sep{height:1px;background:rgba(255,255,255,.08);margin:7px 0;}
.xp-total-n{font-size:16px;font-weight:600;font-family:var(--mono);}

/* ── Leaderboard ── */
.lb-item{display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid var(--line2);}
.lb-item:last-child{border-bottom:none;}
.lb-av{width:28px;height:28px;border-radius:7px;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:#fff;flex-shrink:0;}
.lb-pbar{height:2px;background:var(--bg2);border-radius:99px;margin-top:5px;overflow:hidden;}
.lb-pbar-f{height:100%;border-radius:99px;}

/* ── Hero / dark card ── */
.hero{background:var(--sb);border-radius:var(--rl);padding:20px 22px;position:relative;overflow:hidden;}
.hero-label{font-size:10px;font-weight:600;color:rgba(255,255,255,.3);text-transform:uppercase;letter-spacing:.8px;margin-bottom:8px;}
.hero-num{font-size:48px;font-weight:600;font-family:var(--mono);line-height:1;color:var(--blue);}
.hero-title{font-size:15px;font-weight:600;color:#fff;margin-top:5px;}
.hero-sub{font-size:11px;color:rgba(255,255,255,.35);margin-top:2px;}
.hero-bar{height:3px;background:rgba(255,255,255,.1);border-radius:99px;overflow:hidden;margin-top:14px;}
.hero-bar-f{height:100%;background:linear-gradient(90deg,var(--blue),#7ac4de);border-radius:99px;}
.hero-note{display:flex;justify-content:space-between;margin-top:4px;font-size:10px;color:rgba(255,255,255,.2);font-family:var(--mono);}

/* ── Quest row ── */
.q-row{display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid var(--line2);}
.q-row:last-child{border-bottom:none;}
.q-bar-wrap{height:3px;background:var(--bg2);border-radius:99px;overflow:hidden;margin-top:4px;}
.q-bar-fill{height:100%;border-radius:99px;}

/* ── Sidebar user card ── */
.sb-user{margin:8px 8px 2px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.09);border-radius:10px;padding:10px 11px;}
.sb-av{width:28px;height:28px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:#fff;flex-shrink:0;}
.sb-xpb{height:3px;background:rgba(255,255,255,.1);border-radius:99px;overflow:hidden;margin-top:7px;}
.sb-xpf{height:100%;background:linear-gradient(90deg,var(--blue),#7ac4de);border-radius:99px;}
.sb-sec{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:rgba(255,255,255,.2);padding:10px 20px 3px;display:block;}

/* ── Page header ── */
.pg-title{font-size:18px;font-weight:700;color:var(--ink);letter-spacing:-.3px;margin-bottom:2px;}
.pg-sub{font-size:12px;color:var(--ink4);margin-bottom:14px;}

/* ── Session dots ── */
.dot-on{width:6px;height:6px;border-radius:7px;background:var(--blue2);flex-shrink:0;}
.dot-off{width:6px;height:6px;border-radius:7px;background:rgba(26,39,41,.15);flex-shrink:0;}
.sess-on{font-size:10px;font-weight:600;color:var(--blue2);}
.sess-off{font-size:10px;color:var(--ink4);}

/* ── Event banner ── */
.ev{background:var(--sb);border-radius:var(--r);padding:11px 16px;display:flex;align-items:center;gap:14px;margin-bottom:14px;}
.ev-t{font-size:12px;font-weight:600;color:#fff;}
.ev-s{font-size:11px;color:rgba(255,255,255,.3);margin-top:1px;}
.ev-badge{font-size:11px;font-weight:700;background:var(--gold);color:#2a2000;padding:3px 10px;border-radius:4px;flex-shrink:0;margin-left:auto;}

/* ── Milestone ── */
.ms{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:var(--r);margin-bottom:6px;border:1px solid var(--line);}
.ms-n{font-size:20px;font-weight:600;font-family:var(--mono);width:28px;flex-shrink:0;}
.ms-l{font-size:12px;font-weight:600;}
.ms-s{font-size:10px;margin-top:1px;}

/* ── Pending row ── */
.pend-row{display:flex;align-items:center;gap:9px;padding:8px 0;border-bottom:1px solid var(--line2);}
.pend-row:last-child{border-bottom:none;}

/* ── Off surface ── */
.off2{background:var(--bg2);}
--bdr:var(--line);
--navy:var(--ink);
--amber:var(--gold2);
--green:var(--blue2);
--red:var(--rose);
--gdk:var(--blue2);
--glt:var(--bluel);
--ydk:var(--gold2);
--ylt:var(--goldl);
</style>


"""


# ══════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════
def now_jkt():  return datetime.now(TZ_JKT)
def now_str():  return now_jkt().strftime("%Y-%m-%d %H:%M:%S")
def today_str():return now_jkt().strftime("%Y-%m-%d")

def gen_ref(task_type, user, seq):
    prefix = SLA_CONFIG.get(task_type, {}).get("prefix","XX")
    return f"{prefix}-{now_jkt().strftime('%Y-%m-%d')}-{user[:3].upper()}-{str(seq).zfill(3)}"

def _get_lvl_idx(xp):
    """Return current level index (0-based) for given XP."""
    cur = 0
    for i, (thresh, _) in enumerate(LEVELS):
        if xp >= thresh: cur = i
    return cur

def get_holiday_type(date_str):
    """Return 'holiday'|'sunday'|'saturday'|None untuk date_str YYYY-MM-DD."""
    try:
        from datetime import date as _d
        d = _d.fromisoformat(str(date_str)[:10])
        if str(date_str)[:10] in HOLIDAYS_2026: return "holiday"
        if d.weekday() == 6: return "sunday"
        if d.weekday() == 5: return "saturday"
    except Exception: pass
    return None

def calc_holiday_bonus(date_str):
    """Return bonus dict atau None jika bukan hari libur."""
    t = get_holiday_type(date_str)
    return HOLIDAY_BONUS.get(t) if t else None

def get_pending_holiday_allowance(xplog_df):
    """Ambil list Weekend Allowance yang Applied By == PENDING."""
    if xplog_df.empty or "Type" not in xplog_df.columns: return []
    df = xplog_df[(xplog_df["Type"]=="Weekend Allowance") &
                  (xplog_df.get("Applied By", "").astype(str)=="PENDING" if "Applied By" in xplog_df.columns
                   else True)].copy()
    if "Applied By" in xplog_df.columns:
        df = xplog_df[(xplog_df["Type"]=="Weekend Allowance") &
                      (xplog_df["Applied By"].astype(str)=="PENDING")]
    return [{"ts":str(r.get("Timestamp","")), "staff":str(r.get("Staff","")),
             "amount":int(float(str(r.get("Amount",0) or 0))),
             "reason":str(r.get("Reason",""))} for _,r in df.iterrows()]

def get_weekend_summary(task_df):
    """Ringkasan bonus weekend per staff dari task Done."""
    from datetime import date, timedelta
    summary = {}
    if task_df.empty or "Date" not in task_df.columns or "Status" not in task_df.columns:
        return summary
    done = task_df[task_df["Status"]=="Done"]
    for _, row in done.iterrows():
        d = str(row.get("Date",""))[:10]
        sn = str(row.get("Staff",""))
        ht = get_holiday_type(d)
        if not ht: continue
        b = HOLIDAY_BONUS.get(ht,{})
        if sn not in summary: summary[sn]={"tasks":0,"bonus_xp":0}
        summary[sn]["tasks"]    += 1
        summary[sn]["bonus_xp"] += b.get("xp",0)
    return summary


def get_level(xp):
    cur_idx = 0
    for i, (thresh, _) in enumerate(LEVELS):
        if xp >= thresh: cur_idx = i
    thresh_cur, name_cur = LEVELS[cur_idx]
    thresh_nxt, name_nxt = LEVELS[cur_idx+1] if cur_idx+1 < len(LEVELS) else (thresh_cur,"Max")
    pct = min(100, int((xp-thresh_cur)/max(thresh_nxt-thresh_cur,1)*100))
    return name_cur, thresh_cur, thresh_nxt, name_nxt, pct

def calc_xp_full(task_type, elapsed_min, streak_d=0, ai_type="Balanced"):
    cfg = SLA_CONFIG.get(task_type, {})
    base, ideal, maks = cfg.get("xp",10), cfg.get("ideal",10), cfg.get("maks",20)
    if elapsed_min <= ideal*0.5:   speed = 15
    elif elapsed_min <= ideal:      speed = 10
    elif elapsed_min <= ideal*0.8:  speed = 5
    elif elapsed_min <= maks:       speed = 0
    else:                           speed = -10
    accuracy = 20; coin = 5
    streak = 50 if streak_d>=14 else 25 if streak_d>=7 else 10 if streak_d>=3 else 0
    mult  = {"Pro":1.2,"Balanced":1.0,"Slow":0.9,"Risky":0.8}.get(ai_type,1.0)
    total = max(1, round((base+speed+accuracy+streak)*mult))
    return {"base":base,"speed":speed,"accuracy":accuracy,"streak":streak,"mult":mult,"total":total,"coin":coin}

def sla_info(task_type, ts_str, status):
    cfg = SLA_CONFIG.get(task_type)
    if not cfg: return {"pct":0,"color":"var(--txt)","label":"—","cls":"sla-d"}
    if str(status).lower()=="done": return {"pct":100,"color":"var(--txt)","label":"Done","cls":"sla-d"}
    try:
        dt = TZ_JKT.localize(datetime.strptime(str(ts_str).replace(" WIB","").strip(),"%Y-%m-%d %H:%M:%S"))
        elapsed = (now_jkt()-dt).total_seconds()/60
    except Exception:
        return {"pct":0,"color":"var(--txt)","label":"—","cls":"sla-d"}
    ideal, maks = cfg["ideal"], cfg["maks"]
    pct = min(elapsed/maks*100, 100)
    if elapsed<=ideal: return {"pct":pct,"color":"var(--gdk)","label":f"{max(0,round(ideal-elapsed))}m ideal","cls":"sla-ok"}
    if elapsed<=maks:  return {"pct":pct,"color":"var(--ydk)","label":f"{max(0,round(maks-elapsed))}m tersisa","cls":"sla-w"}
    return {"pct":100,"color":"var(--red)","label":f"Over +{round(elapsed-maks)}m","cls":"sla-ov"}

def streak_days(df, user):
    if df.empty or "Staff" not in df.columns: return 0
    dates = sorted(df[df["Staff"]==user]["Date"].dropna().unique(), reverse=True)
    streak, check = 0, now_jkt().date()
    for d in dates:
        try:
            dd = datetime.strptime(str(d),"%Y-%m-%d").date()
            if dd==check:   streak+=1; check-=timedelta(days=1)
            elif dd<check:  break
        except Exception: continue
    return streak

def classify_ai(df, user):
    if df.empty or "Staff" not in df.columns: return "Balanced"
    u = df[df["Staff"]==user]
    if len(u)<5: return "Balanced"
    try:
        avg_sla = float(u["SLA Minutes"].mean()) if "SLA Minutes" in u.columns else 20
        neg_xp  = (u["XP"].astype(float)<0).mean() if "XP" in u.columns else 0
        if neg_xp>0.3: return "Risky"
        if avg_sla>30:  return "Slow"
        if avg_sla<15:  return "Pro"
    except Exception: pass
    return "Balanced"

def next_seq(task_df, user):
    if task_df.empty or "Staff" not in task_df.columns: return 1
    return len(task_df[task_df["Staff"]==user])+1

def status_html(s, task_type=""):
    if task_type in PENALTY_TYPES: return '<span class="pill pill-red">Penalti</span>'
    sl = str(s).lower()
    if sl=="done":        return '<span class="pill pill-green">Done</span>'
    if "progress" in sl:  return '<span class="pill pill-blue">In Progress</span>'
    if "pending" in sl:   return '<span class="pill pill-amber">Pending</span>'
    if "waiting" in sl:   return '<span class="pill pill-amber">Waiting</span>'
    if "hold" in sl:      return '<span class="pill pill-gray">On Hold</span>'
    if "cancel" in sl:    return '<span class="pill pill-red">Cancelled</span>'
    return f'<span class="pill pill-gray">{s}</span>'

def _safe_int(v):
    try: return int(float(v or 0))
    except: return 0

# ══════════════════════════════════════════════════════════
#  GOOGLE SHEETS — ARSITEKTUR BARU YANG CEPAT
#
#  PRINSIP:
#  1. @st.cache_resource → workbook di-cache selamanya (1 koneksi saja)
#  2. get_cached_wb() → ambil workbook dari cache, TIDAK buat koneksi baru
#  3. Semua update digabung jadi 1 batch_update (1 API call, bukan N call)
#  4. load_data() membaca dari cached workbook
# ══════════════════════════════════════════════════════════

@st.cache_resource
def _cached_wb():
    """
    Buat koneksi ke Google Sheets SEKALI, simpan di cache.
    Tidak akan reconnect kecuali app restart.
    """
    scope = ["https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive"]
    creds  = Credentials.from_service_account_info(dict(st.secrets[SECRETS_KEY]), scopes=scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID)

def get_cached_wb():
    """Return cached workbook. Refresh jika expired."""
    try:
        return _cached_wb()
    except Exception:
        _cached_wb.clear()
        return _cached_wb()

def _ensure_ws(wb, name, rows, cols, headers):
    """Buat worksheet jika belum ada, validasi header."""
    try:
        ws = wb.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        ws = wb.add_worksheet(title=name, rows=str(rows), cols=str(cols))
    first_row = ws.row_values(1)
    if not first_row or first_row[:len(headers)] != headers:
        ws.clear()
        ws.insert_row(headers, 1)
        try:
            ws.format("1:1", {
                "textFormat":{"bold":True,"fontSize":10,"foregroundColor":{"red":1,"green":1,"blue":1}},
                "backgroundColor":{"red":0.008,"green":0.239,"blue":0.482},
                "horizontalAlignment":"CENTER",
            })
            wb.batch_update({"requests":[{"updateSheetProperties":{
                "properties":{"sheetId":ws.id,"gridProperties":{"frozenRowCount":1}},
                "fields":"gridProperties.frozenRowCount"
            }}]})
        except Exception:
            pass
    return ws

def init_all_sheets():
    """Inisialisasi semua sheet. Dipanggil sekali saat startup."""
    try:
        wb = get_cached_wb()
        _ensure_ws(wb,"Task Log",    2000,20,TASK_HEADERS)
        _ensure_ws(wb,"QC Log",       500,12,QC_HEADERS)
        _ensure_ws(wb,"Session Log",  500,10,SESSION_HEADERS)
        _ensure_ws(wb,"Projects",     200,10,PROJECT_HEADERS)
        _ensure_ws(wb,"XP Log",       500, 8,XP_LOG_HEADERS)
        return None  # no error
    except Exception as e:
        return str(e)

@st.cache_data(ttl=30)
def load_data():
    """
    Baca semua sheet. Cache 30 detik.
    PERBAIKAN: pakai cached workbook, TIDAK buat koneksi baru.
    """
    try:
        wb = get_cached_wb()
        return (
            pd.DataFrame(wb.worksheet("Task Log").get_all_records()),
            pd.DataFrame(wb.worksheet("QC Log").get_all_records()),
            pd.DataFrame(wb.worksheet("Session Log").get_all_records()),
            pd.DataFrame(wb.worksheet("Projects").get_all_records()),
            pd.DataFrame(wb.worksheet("XP Log").get_all_records()),
            None,
        )
    except Exception as e:
        return pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),str(e)

def ws_append(sheet_name, row_data):
    """
    Tulis 1 baris ke sheet. Return (True,None) atau (False,err).
    PERBAIKAN: pakai cached workbook.
    """
    try:
        wb = get_cached_wb()
        ws = wb.worksheet(sheet_name)
        ws.append_row([str(v) if v != "" else "" for v in row_data],
                      value_input_option="USER_ENTERED")
        return True, None
    except Exception as e:
        return False, str(e)

def ws_batch_update(sheet_name, row_idx, col_val_dict):
    """
    Update banyak cell dalam 1 API call (batch).
    col_val_dict: {"A": value, "B": value, ...} atau {col_letter: value}
    PERBAIKAN: 1 batch_update menggantikan N kali ws.update() terpisah.
    """
    try:
        wb = get_cached_wb()
        ws = wb.worksheet(sheet_name)
        # Susun range_data untuk batch
        data = [{"range": f"{col}{row_idx}", "values": [[val]]}
                for col, val in col_val_dict.items()]
        ws.batch_update(data, value_input_option="USER_ENTERED")
        return True, None
    except Exception as e:
        return False, str(e)

def ws_get_all_rows(sheet_name):
    """
    Ambil semua baris dari sheet.
    PERBAIKAN: pakai cached workbook.
    """
    try:
        wb = get_cached_wb()
        return wb.worksheet(sheet_name).get_all_values()
    except Exception:
        return []

def find_row_by_ref(ref_id):
    """
    Cari baris di Task Log berdasarkan Ref ID (kolom P = index 16, 1-based).
    Return row_idx (1-based, sudah termasuk header) atau None.
    PERBAIKAN: hanya baca 1 kolom (P), jauh lebih cepat dari get_all_values.
    """
    try:
        wb  = get_cached_wb()
        ws  = wb.worksheet("Task Log")
        col = ws.col_values(16)  # kolom P = Ref ID (1-based index 16)
        for i, val in enumerate(col):
            if str(val).strip() == str(ref_id).strip():
                return i+1  # 1-based row index
        return None
    except Exception:
        return None

# ══════════════════════════════════════════════════════════
#  SESSION STATE
# ══════════════════════════════════════════════════════════
_DEFAULTS = {
    "logged_in":False,"current_user":"","current_role":"",
    "login_time":None,"session_row":None,"last_activity":None,
    "nav_page":"My Tasks","toast_msg":None,"toast_type":"success",
    "sheets_ready":False,
    "prev_xp":None,
}
for k,v in _DEFAULTS.items():
    if k not in st.session_state: st.session_state[k]=v

st.markdown(CSS, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
#  INISIALISASI SHEET (sekali saat startup)
# ══════════════════════════════════════════════════════════
if not st.session_state.sheets_ready:
    with st.spinner("Menghubungkan ke Google Sheets..."):
        err = init_all_sheets()
    if err:
        st.error(f"❌ Gagal koneksi: {err}")
        st.info("Pastikan secrets.toml benar dan service account punya akses Editor ke spreadsheet.")
        st.stop()
    st.session_state.sheets_ready = True

# ══════════════════════════════════════════════════════════
#  LOGIN
# ══════════════════════════════════════════════════════════
def render_login():
    _, col, _ = st.columns([1,2,1])
    with col:
        st.markdown("""
        <div style="text-align:center;padding:20px 0 10px;">
          <span style="font-size:48px;">🐾</span>
          <h1 style="font-size:28px;font-weight:700;color:var(--ink);margin:8px 0 4px;">PAWGRESS</h1>
          <p style="font-size:12px;color:var(--txt);">Performance Gamification Dashboard · Season April v2.4</p>
        </div>""", unsafe_allow_html=True)

        with st.form("login_form", clear_on_submit=False):
            username  = st.selectbox("Pilih Username", ["—"]+ALL_STAFF_FLAT)
            password  = st.text_input("Password", type="password")
            submitted = st.form_submit_button("🔐 Login", use_container_width=True)

        if submitted:
            if username == "—":
                st.error("Pilih username terlebih dahulu.")
            elif PASSWORDS.get(username,"") != password:
                st.error("Username atau password salah.")
            else:
                st.session_state.logged_in    = True
                st.session_state.current_user = username
                st.session_state.current_role = STAFF_ROLE_MAP.get(username,"Booker")
                st.session_state.login_time   = now_jkt()
                st.session_state.last_activity= now_jkt()
                st.session_state.nav_page     = "Dashboard" if username=="Manager" else "My Tasks"
                # Log session
                ok, _ = ws_append("Session Log",[
                    today_str(), username, STAFF_ROLE_MAP.get(username,""),
                    now_str(), "", 0, "Active"
                ])
                if ok:
                    col_data = ws_get_all_rows("Session Log")
                    st.session_state.session_row = len(col_data)
                load_data.clear()
                st.rerun()

if not st.session_state.logged_in:
    render_login()
    st.stop()

# ══════════════════════════════════════════════════════════
#  DATA LOADING
# ══════════════════════════════════════════════════════════
task_df, qc_df, session_df, proj_df, xplog_df, data_err = load_data()
if data_err:
    st.warning(f"⚠️ Data load warning: {data_err}")

USER  = st.session_state.current_user
ROLE  = st.session_state.current_role
TODAY = today_str()

# ── Computed user stats ──────────────────────────────────
# FIX: Gunakan df["Status"] bukan df.get("Status") — DataFrame tidak punya .get()
def _sum_xp(df):
    if df.empty or "XP" not in df.columns: return 0
    try: return int(df["XP"].astype(float).sum())
    except: return 0

user_task_df  = task_df[task_df["Staff"]==USER].copy() if not task_df.empty and "Staff" in task_df.columns else pd.DataFrame()
today_task_df = user_task_df[user_task_df["Date"]==TODAY].copy() if not user_task_df.empty and "Date" in user_task_df.columns else pd.DataFrame()

# FIX: df["Status"] bukan df.get("Status", pd.Series())
if not user_task_df.empty and "Status" in user_task_df.columns:
    TOTAL_XP  = _sum_xp(user_task_df[user_task_df["Status"]=="Done"])
else:
    TOTAL_XP  = 0

if not today_task_df.empty and "Status" in today_task_df.columns:
    TODAY_XP  = _sum_xp(today_task_df[today_task_df["Status"]=="Done"])
    DONE_TODAY= len(today_task_df[today_task_df["Status"]=="Done"])
else:
    TODAY_XP  = 0
    DONE_TODAY= 0

STREAK   = streak_days(task_df, USER)
AI_TYPE  = classify_ai(task_df, USER)
COIN_TOT = int(user_task_df["Coin"].astype(float).sum()) if not user_task_df.empty and "Coin" in user_task_df.columns else 0
LVL_NAME, LVL_MIN, LVL_MAX, LVL_NEXT, LVL_PCT = get_level(TOTAL_XP)

# ══════════════════════════════════════════════════════════
#  SIDEBAR
with st.sidebar:
    # ── Logo ────────────────────────────────────────────────
    st.markdown("""
    <div style="padding:14px 14px 11px;border-bottom:1px solid rgba(255,255,255,.07);">
      <div style="display:flex;align-items:center;gap:10px;">
        <div style="width:28px;height:28px;background:#51a1c4;border-radius:8px;
          display:flex;align-items:center;justify-content:center;font-size:13px;flex-shrink:0;">🐾</div>
        <div>
          <div style="font-size:13px;font-weight:700;color:#fff;letter-spacing:-.1px;line-height:1.1;">PAWGRESS</div>
          <div style="font-size:9px;color:rgba(255,255,255,.28);margin-top:2px;
            letter-spacing:.5px;text-transform:uppercase;">Season April</div>
        </div>
      </div>
    </div>""", unsafe_allow_html=True)

    # ── User card ────────────────────────────────────────────
    av_col  = STAFF_COLORS.get(USER, "var(--sb)")
    av_init = USER[:2].upper()
    ai_colors = {"Pro":"#4ade80","Balanced":"#51a1c4","Slow":"#ddb551","Risky":"#f87171"}
    if ROLE != "Manager":
        ai_c = ai_colors.get(AI_TYPE, "#51a1c4")
        st.markdown(f"""
        <div class="sb-user">
          <div style="display:flex;align-items:center;gap:9px;margin-bottom:8px;">
            <div class="sb-av" style="background:{av_col};">{av_init}</div>
            <div style="flex:1;min-width:0;">
              <div style="font-size:12px;font-weight:600;color:rgba(255,255,255,.9);line-height:1.2;">{USER}</div>
              <div style="font-size:10px;color:rgba(255,255,255,.32);margin-top:1px;">{ROLE}</div>
            </div>
            <div style="text-align:right;flex-shrink:0;">
              <div style="font-size:15px;font-weight:700;color:#51a1c4;font-family:var(--mono);line-height:1;">{_get_lvl_idx(TOTAL_XP)}</div>
              <div style="font-size:8px;color:rgba(255,255,255,.22);letter-spacing:.3px;">LV</div>
            </div>
          </div>
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
            <span style="font-size:10px;color:rgba(255,255,255,.3);">{LVL_NAME}</span>
            <span style="font-size:9px;font-weight:600;padding:1px 7px;border-radius:99px;
              background:{ai_c}20;color:{ai_c};border:1px solid {ai_c}33;">⚡ {AI_TYPE}</span>
          </div>
          <div class="sb-xpb"><div class="sb-xpf" style="width:{LVL_PCT}%;"></div></div>
          <div style="display:flex;justify-content:space-between;font-size:10px;
            color:rgba(255,255,255,.2);font-family:var(--mono);margin-top:4px;">
            <span>{TOTAL_XP:,} xp</span>
            <span style="color:#ddb551;">🔥 {STREAK}d</span>
          </div>
        </div>""", unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="margin:8px 8px 2px;background:rgba(81,161,196,.07);
          border:1px solid rgba(81,161,196,.15);border-radius:11px;padding:10px 12px;">
          <div style="display:flex;align-items:center;gap:9px;">
            <div style="width:30px;height:30px;border-radius:8px;background:rgba(81,161,196,.15);
              display:flex;align-items:center;justify-content:center;font-size:14px;flex-shrink:0;">👑</div>
            <div>
              <div style="font-size:12px;font-weight:600;color:rgba(255,255,255,.9);">Manager</div>
              <div style="font-size:10px;color:rgba(255,255,255,.3);margin-top:1px;">Full Access · Admin</div>
            </div>
            <div style="margin-left:auto;font-size:9px;font-weight:700;padding:2px 7px;
              border-radius:99px;background:rgba(81,161,196,.15);color:#51a1c4;
              border:1px solid rgba(81,161,196,.3);">ADMIN</div>
          </div>
        </div>""", unsafe_allow_html=True)

    # ── Navigation ───────────────────────────────────────────
    if ROLE == "Manager":
        st.markdown('<div class="sb-sec">Overview</div>', unsafe_allow_html=True)
        for ico, pg in [("📊","Dashboard"),("🖥","Session Monitor")]:
            if st.button(f"{ico}  {pg}", key=f"nav_{pg}", use_container_width=True,
                         type="primary" if st.session_state.nav_page==pg else "secondary"):
                st.session_state.nav_page=pg; st.rerun()
        st.markdown('<div class="sb-sec">Management</div>', unsafe_allow_html=True)
        for ico, pg in [("📋","Semua Task"),("⭐","XP Control"),("📁","Kelola Project")]:
            if st.button(f"{ico}  {pg}", key=f"nav_{pg}", use_container_width=True,
                         type="primary" if st.session_state.nav_page==pg else "secondary"):
                st.session_state.nav_page=pg; st.rerun()
        st.markdown('<div class="sb-sec">Analytics</div>', unsafe_allow_html=True)
        for ico, pg in [("📈","Performa Tim"),("📝","Activity Log")]:
            if st.button(f"{ico}  {pg}", key=f"nav_{pg}", use_container_width=True,
                         type="primary" if st.session_state.nav_page==pg else "secondary"):
                st.session_state.nav_page=pg; st.rerun()
    else:
        st.markdown('<div class="sb-sec">Workspace</div>', unsafe_allow_html=True)
        for ico, pg in [("📋","My Tasks"),("✅","QC Antrian"),("🔍","Status QC Saya")]:
            if st.button(f"{ico}  {pg}", key=f"nav_{pg}", use_container_width=True,
                         type="primary" if st.session_state.nav_page==pg else "secondary"):
                st.session_state.nav_page=pg; st.rerun()
        st.markdown('<div class="sb-sec">Game</div>', unsafe_allow_html=True)
        for ico, pg in [("🏆","Leaderboard"),("⭐","Quest & Streak")]:
            if st.button(f"{ico}  {pg}", key=f"nav_{pg}", use_container_width=True,
                         type="primary" if st.session_state.nav_page==pg else "secondary"):
                st.session_state.nav_page=pg; st.rerun()
    # Logout
    st.markdown('<hr>', unsafe_allow_html=True)
    if st.button("🚪  Logout", use_container_width=True, key="btn_logout"):
        if st.session_state.get("session_row"):
            try:
                dur = int((now_jkt()-st.session_state.login_time).total_seconds()/60) if st.session_state.login_time else 0
                ws_batch_update("Session Log", st.session_state.session_row, {"E":now_str(),"F":dur,"G":"Logout"})
            except Exception: pass
        for k in _DEFAULTS: st.session_state[k] = _DEFAULTS[k]
        load_data.clear()
        st.rerun()


# ══════════════════════════════════════════════════════════
#  HEADER & TOAST
# ══════════════════════════════════════════════════════════
PAGE_META = {
    "My Tasks":         ("My Tasks",         "Task dan pekerjaan Anda"),
    "QC Antrian":       ("QC Antrian",        "Review task rekan tim"),
    "Status QC Saya":   ("Status QC",         "Hasil review task Anda"),
    "Leaderboard":      ("Leaderboard",        "Ranking performa tim"),
    "Quest & Streak":   ("Quest & Streak",     "Misi dan pencapaian"),
    "Dashboard":        ("Dashboard",          "Ringkasan hari ini"),
    "Session Monitor":  ("Session Monitor",    "Aktivitas login staff"),
    "Semua Task":       ("Semua Task",         "Kelola semua task"),
    "XP Control":       ("XP Control",         "Approval dan kelola XP"),
    "Kelola Project":   ("Kelola Project",     "Manage project tim"),
    "Performa Tim":     ("Performa Tim",       "Analitik performa"),
    "Activity Log":     ("Activity Log",       "Log semua aktivitas"),
}
pg = st.session_state.nav_page
_title, _sub = PAGE_META.get(pg, (pg, ""))
st.markdown(f'<div class="pg-title">{_title}</div><div class="pg-sub">{_sub}</div>', unsafe_allow_html=True)

if st.session_state.get("toast_msg"):
    msg, typ = st.session_state.toast_msg, st.session_state.toast_type
    {"success":st.success,"warning":st.warning,"error":st.error}.get(typ, st.info)(msg)
    st.session_state.toast_msg = None; st.session_state.toast_type = "success"

# ══════════════════════════════════════════════════════════
#  PAGE: MY TASKS
# ══════════════════════════════════════════════════════════
def page_my_tasks():
    st.markdown("""<div class="ev"><div><div class="ev-t">Bulan Akurasi — Season April</div><div class="ev-s">Double XP aktif · 28 hari tersisa</div></div><div class="ev-badge">2× XP</div></div>""", unsafe_allow_html=True)

    st.markdown(f"""<div class="stat-row stat-row-4">
      <div class="stat-cell"><div class="stat-num" style="color:var(--green);">+{TODAY_XP}</div><div class="stat-lbl">XP hari ini</div><div class="stat-sub" style="color:var(--green);">{DONE_TODAY} task selesai</div></div>
      <div class="stat-cell"><div class="stat-num" style="color:var(--gold2);">{STREAK}</div><div class="stat-lbl">hari streak</div><div class="stat-sub" style="color:var(--gold2);">+25 XP bonus</div></div>
      <div class="stat-cell"><div class="stat-num">{TOTAL_XP//100}</div><div class="stat-lbl">level · {LVL_NAME}</div></div>
      <div class="stat-cell"><div class="stat-num">{COIN_TOT}</div><div class="stat-lbl">coin</div></div>
    </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── INPUT TASK ──────────────────────────────────────────
    with st.expander("➕ Input Task Baru", expanded=False):
        with st.form("form_input_task", clear_on_submit=True):
            c1,c2 = st.columns(2)
            with c1:
                task_type    = st.selectbox("Jenis Task *", TASK_TYPE_LIST)
                hotel        = st.text_input("Nama Hotel / Vendor *")
            with c2:
                client       = st.text_input("Nama Tamu / Klien *")
                booking_code = st.text_input("Kode Booking (opsional)")
            notes    = st.text_area("Catatan (opsional)", height=60)
            cfg      = SLA_CONFIG.get(task_type,{})
            st.markdown(f"""<div style="background:var(--bg2);border:1.5px solid var(--bdr);border-radius:9px;padding:9px 13px;margin:4px 0 6px;">
              <span style="font-size:12px;font-weight:600;color:var(--ink);">{task_type}</span>
              <span style="font-size:10px;color:var(--txt);margin-left:10px;">SLA Ideal: <strong>{cfg.get('ideal','?')} mnt</strong> · Maks: <strong>{cfg.get('maks','?')} mnt</strong></span>
              <span style="font-size:9px;font-weight:600;background:#edf6fa;color:#3a87ab;padding:2px 8px;border-radius:20px;margin-left:8px;">{cfg.get('cat','')}</span>
            </div>""", unsafe_allow_html=True)
            submitted = st.form_submit_button("✅ Submit Task", use_container_width=True)

        if submitted:
            h  = (hotel or "").strip()
            cl = (client or "").strip()
            bk = (booking_code or "").strip().upper()
            nt = (notes or "").strip()
            if not h:
                st.error("Nama Hotel / Vendor wajib diisi.")
            elif not cl:
                st.error("Nama Tamu / Klien wajib diisi.")
            else:
                ref = gen_ref(task_type, USER, next_seq(task_df, USER))
                ok, err = ws_append("Task Log", [
                    TODAY, USER, ROLE, task_type, bk, h, cl, nt,
                    "In Progress", cfg.get("ideal",10), 0, 0,
                    "Pending QC", "", "", ref, now_str(), ""
                ])
                if ok:
                    load_data.clear()
                    st.session_state.toast_msg = f"✅ Task **{ref}** berhasil dibuat! SLA {cfg.get('maks','?')} menit mulai berjalan."
                    st.session_state.toast_type = "success"
                    st.rerun()
                else:
                    st.error(f"❌ Gagal simpan ke Google Sheets: {err}")

    # ── FILTER ──────────────────────────────────────────────
    st.markdown("---")
    cf1,cf2,cf3 = st.columns([2,2,1])
    with cf1: f_period = st.selectbox("Periode",["Semua","Hari Ini","7 Hari","30 Hari"],key="flt_p")
    with cf2: f_status = st.selectbox("Status",["Semua Status"]+STATUS_LIST,key="flt_s")
    with cf3: f_search = st.text_input("Cari",placeholder="Ref / Hotel...",key="flt_q")

    my_df = user_task_df.copy()
    if not my_df.empty:
        if "Date" in my_df.columns:
            if   f_period=="Hari Ini": my_df = my_df[my_df["Date"]==TODAY]
            elif f_period=="7 Hari":   my_df = my_df[my_df["Date"]>=(now_jkt()-timedelta(days=7)).strftime("%Y-%m-%d")]
            elif f_period=="30 Hari":  my_df = my_df[my_df["Date"]>=(now_jkt()-timedelta(days=30)).strftime("%Y-%m-%d")]
        if f_status!="Semua Status" and "Status" in my_df.columns:
            my_df = my_df[my_df["Status"]==f_status]
        if f_search and f_search.strip():
            q = f_search.strip().lower()
            mask = pd.Series([False]*len(my_df),index=my_df.index)
            for col_n in ["Ref ID","Task Type","Hotel","Client","Booking ID"]:
                if col_n in my_df.columns:
                    mask = mask | my_df[col_n].astype(str).str.lower().str.contains(q,na=False)
            my_df = my_df[mask]

    st.markdown(f"**{len(my_df)} task ditemukan**")
    if my_df.empty:
        st.info("Tidak ada task sesuai filter.")
        return

    if "Timestamp" in my_df.columns:
        my_df = my_df.sort_values("Timestamp", ascending=False)

    # ── Weekend / Holiday Banner ────────────────────────────
    _hbonus_today = calc_holiday_bonus(TODAY)
    if _hbonus_today:
        _already = (not xplog_df.empty and "Type" in xplog_df.columns and
                    "Staff" in xplog_df.columns and "Applied By" in xplog_df.columns and
                    not xplog_df[(xplog_df["Type"]=="Weekend Allowance") &
                                 (xplog_df["Staff"]==USER) &
                                 (xplog_df["Timestamp"].astype(str).str.startswith(TODAY))].empty)
        _hstatus = "✓ Sudah tercatat — menunggu approval Manager" if _already else f"Kerjakan task hari ini → +{_hbonus_today['xp']} XP per task · Perlu approval Manager"
        st.markdown(f"""
        <div style="background:var(--sb);border:1px solid {_hbonus_today['color']}44;border-radius:12px;
          padding:13px 16px;margin-bottom:12px;display:flex;align-items:center;gap:14px;">
          <div style="width:42px;height:42px;border-radius:10px;background:{_hbonus_today['color']}20;
            display:flex;align-items:center;justify-content:center;font-size:22px;flex-shrink:0;">🎁</div>
          <div style="flex:1;">
            <div style="font-size:13px;font-weight:700;color:#fff;margin-bottom:2px;">
              {_hbonus_today['label']} Allowance Aktif</div>
            <div style="font-size:11px;color:rgba(255,255,255,.4);">{_hstatus}</div>
          </div>
          <div style="text-align:right;flex-shrink:0;">
            <div style="font-size:20px;font-weight:700;font-family:var(--mono);
              color:{_hbonus_today['color']};line-height:1;">+{_hbonus_today['xp']} XP</div>
            <div style="font-size:10px;color:rgba(255,255,255,.3);margin-top:2px;">
              +{_hbonus_today['coin']} Coin / task</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Task List ────────────────────────────────────────────
    for idx, row in my_df.iterrows():
        task_type_r = str(row.get("Task Type",""))
        status_r    = str(row.get("Status",""))
        ref_id      = str(row.get("Ref ID",""))
        hotel_r     = str(row.get("Hotel",""))
        client_r    = str(row.get("Client",""))
        bk_r        = str(row.get("Booking ID",""))
        notes_r     = str(row.get("Notes",""))
        ts_r        = str(row.get("Timestamp",""))
        xp_r        = _safe_int(row.get("XP",0))
        # Weekend badge per task
        _task_date  = str(row.get("Date", TODAY))
        _task_hb    = calc_holiday_bonus(_task_date)
        _wa_badge   = (f' <span style="font-size:9px;font-weight:700;padding:1px 7px;'
                       f'border-radius:99px;background:{_task_hb["color"]}18;'
                       f'color:{_task_hb["color"]};border:1px solid {_task_hb["color"]}33;">'
                       f'🎁 {_task_hb["label"]} +{_task_hb["xp"]} XP</span>'
                      ) if _task_hb else ""
        coin_r      = _safe_int(row.get("Coin",0))
        is_done     = status_r.lower()=="done"
        cfg_r       = SLA_CONFIG.get(task_type_r,{})
        sla_i       = sla_info(task_type_r, ts_r, status_r)
        ico         = "✅" if is_done else "🔄" if "progress" in status_r.lower() else "⏳"

        with st.expander(f"{ico} {task_type_r} — {hotel_r or client_r}  ·  {ref_id}"):
            left_col, right_col = st.columns([3,2])

            with left_col:
                st.markdown("**✏️ Edit Task**")
                with st.form(f"edit_{ref_id}_{idx}"):
                    e1,e2 = st.columns(2)
                    with e1:
                        new_hotel  = st.text_input("Hotel/Vendor", value=hotel_r)
                        new_client = st.text_input("Tamu/Klien",   value=client_r)
                    with e2:
                        new_bk     = st.text_input("Kode Booking", value=bk_r)
                        new_type   = st.selectbox("Jenis Task", TASK_TYPE_LIST,
                            index=TASK_TYPE_LIST.index(task_type_r) if task_type_r in TASK_TYPE_LIST else 0,
                            disabled=is_done)
                    new_notes  = st.text_input("Catatan",  value=notes_r)
                    new_status = st.selectbox("Status",STATUS_LIST,
                        index=STATUS_LIST.index(status_r) if status_r in STATUS_LIST else 0)
                    b1,b2 = st.columns(2)
                    with b1: btn_save = st.form_submit_button("💾 Simpan",      use_container_width=True)
                    with b2: btn_done = st.form_submit_button("✅ Mark as Done", use_container_width=True, disabled=is_done)

                # FIX: diproses setelah form, di dalam expander yang sama
                if btn_save or btn_done:
                    final_status = "Done" if btn_done else new_status
                    row_idx = find_row_by_ref(ref_id)  # 1 API call, hanya baca 1 kolom
                    if row_idx is None:
                        st.error("Ref ID tidak ditemukan di sheet.")
                    else:
                        xp_new, coin_new = xp_r, coin_r
                        if (btn_done or final_status=="Done") and not is_done:
                            elapsed = cfg_r.get("ideal",10)
                            try:
                                dt_ts   = TZ_JKT.localize(datetime.strptime(ts_r.replace(" WIB","").strip(),"%Y-%m-%d %H:%M:%S"))
                                elapsed = (now_jkt()-dt_ts).total_seconds()/60
                            except Exception: pass
                            xp_c    = calc_xp_full(new_type, elapsed, STREAK, AI_TYPE)
                            xp_new  = xp_c["total"]; coin_new = xp_c["coin"]

                        # FIX: 1 batch_update menggantikan 9 ws.update() terpisah
                        ok, err = ws_batch_update("Task Log", row_idx, {
                            "D": new_type,    "E": new_bk,       "F": new_hotel,
                            "G": new_client,  "H": new_notes,    "I": final_status,
                            "K": xp_new,      "L": coin_new,     "R": now_str(),
                        })
                        if ok:
                            load_data.clear()
                            if btn_done or (final_status=="Done" and not is_done):
                                _hb = calc_holiday_bonus(str(row.get("Date", TODAY)))
                                if _hb:
                                    ws_append("XP Log",[now_str(),USER,"Weekend Allowance",
                                        _hb["xp"],
                                        f"{_hb['label']} Allowance — {ref_id} ({new_type})",
                                        "PENDING"])
                                    st.session_state.toast_msg = (
                                        f"🎉 Done! **+{xp_new} XP** +{coin_new} Coin. "
                                        f"🎁 **+{_hb['xp']} XP {_hb['label']} Allowance** menunggu approval Manager.")
                                else:
                                    st.session_state.toast_msg = f"🎉 Done! **+{xp_new} XP** dan **+{coin_new} Coin** masuk."
                            else:
                                st.session_state.toast_msg = f"💾 Task **{ref_id}** diupdate."
                            st.session_state.toast_type = "success"
                            st.rerun()
                        else:
                            st.error(f"Gagal update: {err}")

            with right_col:
                # SLA box
                st.markdown(f"""<div style="background:var(--bg2);border:1.5px solid var(--bdr);border-radius:9px;padding:10px 13px;margin-bottom:10px;">
                  <div style="font-size:11px;font-weight:600;color:var(--ink);margin-bottom:5px;">⏱ SLA</div>
                  <div style="font-size:10px;color:var(--txt);">Ideal <strong>{cfg_r.get('ideal','?')}m</strong> · Maks <strong>{cfg_r.get('maks','?')}m</strong></div>
                  <div class="{sla_i['cls']}" style="margin-top:4px;">{sla_i['label']}</div>
                  <div style="height:4px;background:var(--bg2);border-radius:2px;overflow:hidden;margin-top:7px;">
                    <div style="height:100%;width:{sla_i['pct']}%;background:{sla_i['color']};border-radius:2px;"></div>
                  </div></div>""", unsafe_allow_html=True)

                # XP box
                elapsed_e = cfg_r.get("ideal",10)
                try:
                    dt_e = TZ_JKT.localize(datetime.strptime(ts_r.replace(" WIB","").strip(),"%Y-%m-%d %H:%M:%S"))
                    elapsed_e = (now_jkt()-dt_e).total_seconds()/60
                except Exception: pass
                xp_e = calc_xp_full(task_type_r, elapsed_e, STREAK, AI_TYPE)

                if is_done and xp_r>0:
                    st.markdown(f"""<div class="xp-panel">
                      <div style="font-size:9px;font-weight:600;color:rgba(255,255,255,.3);text-transform:uppercase;letter-spacing:.6px;margin-bottom:9px;">XP Diterima ✓</div>
                      <div class="xp-row"><span class="xp-lbl">XP Masuk</span><span class="xp-val" style="color:var(--green);">+{xp_r}</span></div>
                      <div class="xp-row"><span class="xp-lbl">Coin</span><span class="xp-val" style="color:#51a1c4;">+{coin_r}</span></div>
                      <div class="xp-sep"></div>
                      <div class="xp-line"><span style="font-size:12px;font-weight:600;color:#fff;">Total</span><span class="xp-total-n" style="color:#51a1c4;">+{xp_r} XP</span></div>
                    </div>""", unsafe_allow_html=True)
                else:
                    sc = "var(--green)" if xp_e["speed"]>=0 else "#f87171"
                    ss = "+" if xp_e["speed"]>=0 else ""
                    st.markdown(f"""<div class="xp-panel">
                      <div style="font-size:9px;font-weight:600;color:rgba(255,255,255,.3);text-transform:uppercase;letter-spacing:.6px;margin-bottom:9px;">Estimasi XP</div>
                      <div class="xp-row"><span class="xp-lbl">Base XP</span><span class="xp-val" style="color:rgba(255,255,255,.7);">+{xp_e['base']}</span></div>
                      <div class="xp-row"><span class="xp-lbl">Speed Bonus</span><span class="xp-val" style="color:{sc};">{ss}{xp_e['speed']}</span></div>
                      <div class="xp-row"><span class="xp-lbl">Accuracy</span><span class="xp-val" style="color:var(--green);">+{xp_e['accuracy']}</span></div>
                      <div class="xp-row"><span class="xp-lbl">Streak {STREAK}d</span><span class="xp-val" style="color:#51a1c4;">+{xp_e['streak']}</span></div>
                      <div class="xp-sep"></div>
                      <div class="xp-row" style="font-size:10px;"><span style="color:rgba(255,255,255,.3);">Multiplier ({AI_TYPE})</span><span style="color:rgba(255,255,255,.4);font-family:var(--mono);">{xp_e['mult']}×</span></div>
                      <div class="xp-sep"></div>
                      <div class="xp-line"><span style="font-size:12px;font-weight:600;color:#fff;">Estimasi</span><span class="xp-total-n" style="color:#51a1c4;">+{xp_e['total']} XP</span></div>
                    </div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
#  PAGE: QC ANTRIAN
# ══════════════════════════════════════════════════════════
def page_qc_antrian():
    pending_qc = pd.DataFrame()
    if not task_df.empty and "QC Status" in task_df.columns:
        pending_qc = task_df[
            (task_df["QC Status"]=="Pending QC") &
            (task_df["Status"]=="Done") &
            (task_df["Staff"]!=USER)
        ].copy()

    qc_mine = qc_df[(qc_df["QC By"]==USER)&(qc_df["Date"]==TODAY)] if not qc_df.empty and "QC By" in qc_df.columns else pd.DataFrame()
    ok_n  = len(qc_df[(qc_df["QC By"]==USER)&(qc_df["QC Status"]=="OK")]) if not qc_df.empty else 0
    tot_n = len(qc_df[qc_df["QC By"]==USER]) if not qc_df.empty else 0
    acc   = int(ok_n/tot_n*100) if tot_n>0 else 100

    st.markdown(f"""<div class="stat-row stat-row-3">
      <div class="stat-cell"><div class="stat-num" style="color:var(--rose);">{len(pending_qc)}</div><div class="stat-lbl">antrian QC</div></div>
      <div class="stat-cell"><div class="stat-num" style="color:var(--green);">{len(qc_mine)}</div><div class="stat-lbl">selesai hari ini</div><div class="stat-sub" style="color:var(--green);">+{len(qc_mine)*20} XP</div></div>
      <div class="stat-cell"><div class="stat-num">{acc}%</div><div class="stat-lbl">akurasi QC</div></div>
    </div>""", unsafe_allow_html=True)

    st.markdown(f"---\n**{len(pending_qc)} task pending QC**")
    if pending_qc.empty: st.info("Tidak ada task yang perlu di-review. 🎉"); return

    for idx, row in pending_qc.head(20).iterrows():
        staff_r = str(row.get("Staff","")); task_r = str(row.get("Task Type",""))
        ref_r   = str(row.get("Ref ID","")); hotel_r = str(row.get("Hotel",""))
        cross   = STAFF_ROLE_MAP.get(staff_r,"") != ROLE
        xp_qc   = 20+(5 if cross else 0)

        with st.expander(f"🔍 {task_r} — {hotel_r or staff_r}  ·  {ref_r}"):
            hotel_part2 = f" — {hotel_r}" if hotel_r else ""
            cross_badge  = '<span style="font-size:9px;font-weight:600;background:var(--bluel);color:var(--blue2);padding:1px 7px;border-radius:4px;margin-left:6px;">Cross-role +5 Coin</span>' if cross else ""
            staff_role_lbl = STAFF_ROLE_MAP.get(staff_r, "")
            html_qc = (
                f'<div class="row-card">'
                f'<div style="font-size:12px;font-weight:600;color:var(--ink);">{task_r}{hotel_part2}</div>'
                f'<div style="font-size:10px;color:var(--txt);margin-top:3px;">{ref_r} · Oleh <strong>{staff_r}</strong> ({staff_role_lbl})'
                f'{cross_badge}</div></div>'
            )
            st.markdown(html_qc, unsafe_allow_html=True)

            # FIX: variabel dari form dibaca DALAM with st.form, bukan di luar
            qc_result = qc_notes_v = None
            ok_btn = iss_btn = False
            with st.form(f"qc_{ref_r}_{idx}"):
                qc_result  = st.selectbox("Hasil QC",["OK","Ada Isu"])
                qc_notes_v = st.text_input("Catatan QC (opsional)")
                st.markdown(f"XP diterima: **+{xp_qc} XP**{' + 5 Coin' if cross else ''}")
                b1,b2 = st.columns(2)
                with b1: ok_btn  = st.form_submit_button("✅ Setujui",  use_container_width=True)
                with b2: iss_btn = st.form_submit_button("❌ Ada Isu",  use_container_width=True)

            if ok_btn or iss_btn:
                final_qc = "OK" if ok_btn else "Ada Isu"
                row_idx  = find_row_by_ref(ref_r)
                if row_idx:
                    # FIX: 1 batch update menggantikan 3 ws.update terpisah
                    ws_batch_update("Task Log", row_idx, {
                        "M": final_qc, "N": USER, "O": qc_notes_v or ""
                    })
                ws_append("QC Log",[TODAY,USER,ROLE,staff_r,ref_r,task_r,final_qc,qc_notes_v or "",xp_qc,now_str()])
                load_data.clear()
                st.session_state.toast_msg = f"QC **{ref_r}** — {final_qc}. **+{xp_qc} XP** masuk."
                st.session_state.toast_type = "success"
                st.rerun()

# ══════════════════════════════════════════════════════════
#  PAGE: STATUS QC SAYA
# ══════════════════════════════════════════════════════════
def page_status_qc():
    # FIX: df["Status"] bukan df.get("Status","")
    done_tasks = user_task_df[user_task_df["Status"]=="Done"] if not user_task_df.empty and "Status" in user_task_df.columns else pd.DataFrame()
    if done_tasks.empty: st.info("Belum ada task Done."); return
    for _, row in done_tasks.sort_values("Timestamp",ascending=False).head(30).iterrows():
        qc_s   = str(row.get("QC Status","Pending QC")); qc_by = str(row.get("QC By",""))
        task_r = str(row.get("Task Type","")); ref_r = str(row.get("Ref ID",""))
        xp_r   = _safe_int(row.get("XP",0)); hotel_r = str(row.get("Hotel",""))
        fc,bc  = {"OK":("var(--gdk)","var(--glt)"),"Ada Isu":("var(--red)","var(--rlt)"),"Pending QC":("var(--ydk)","var(--ylt)")}.get(qc_s,("var(--txt)","var(--bg2)"))
        hotel_part   = f" — {hotel_r}" if hotel_r else ""
        reviewer_part = f'<span style="margin-left:6px;">Reviewer: <strong>{qc_by}</strong></span>' if qc_by else ""
        html = (
            f'<div class="row-card">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;">'
            f'<div><div style="font-size:12px;font-weight:600;color:var(--ink);">{task_r}{hotel_part}</div>'
            f'<div style="font-size:10px;color:var(--txt);margin-top:2px;"><span class="mtag">{ref_r}</span>'
            f'{reviewer_part}</div></div>'
            f'<div style="text-align:right;">'
            f'<span style="font-size:9px;font-weight:700;padding:3px 9px;border-radius:20px;background:{bc};color:{fc};border:1px solid {fc}40;">{qc_s}</span>'
            f'<div style="font-size:11px;font-weight:600;color:#3a87ab;font-family:var(--mono);margin-top:3px;">+{xp_r} XP</div>'
            f'</div></div></div>'
        )
        st.markdown(html, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
#  PAGE: LEADERBOARD
# ══════════════════════════════════════════════════════════
def page_leaderboard():
    total_s = len(ALL_STAFF["Booker"])+len(ALL_STAFF["Finance"])
    top_xp = xp_all = 0
    if not task_df.empty and "Staff" in task_df.columns:
        top_xp = int(task_df.groupby("Staff")["XP"].sum().max() or 0)
        xp_all = int(task_df["XP"].astype(float).sum())
    st.markdown(f"""<div class="stat-row stat-row-4">
      <div class="stat-cell"><div class="stat-num">{total_s}</div><div class="stat-lbl">total staff</div></div>
      <div class="stat-cell"><div class="stat-num">{top_xp:,}</div><div class="stat-lbl">top XP</div></div>
      <div class="stat-cell"><div class="stat-num">{xp_all:,}</div><div class="stat-lbl">XP terdistribusi</div></div>
      <div class="stat-cell"><div class="stat-num" style="color:var(--rose);">2×</div><div class="stat-lbl">event aktif</div></div>
    </div>""", unsafe_allow_html=True)

    st.markdown("---")
    lb = pd.DataFrame(columns=["Staff","XP","Tasks"])
    if not task_df.empty and "Staff" in task_df.columns:
        lb = task_df.groupby("Staff").agg(XP=("XP","sum"),Tasks=("Ref ID","count")).reset_index()
        lb = lb[lb["Staff"]!="Manager"].sort_values("XP",ascending=False)
    medals = ["🥇","🥈","🥉"]
    max_xp = int(lb["XP"].max()) if not lb.empty else 1
    for rank,(_, row) in enumerate(lb.iterrows(),1):
        sn=row["Staff"]; xv=int(row["XP"]); tv=int(row["Tasks"])
        ac=STAFF_COLORS.get(sn,"var(--sb)"); ai=sn[:2].upper()
        pct=int(xv/max_xp*100) if max_xp>0 else 0
        medal=medals[rank-1] if rank<=3 else f"#{rank}"
        stk=streak_days(task_df,sn); is_me=sn==USER
        # Build HTML as variable — avoids multiline f-string rendering issues
        border_style = "border:2px solid var(--navy);" if is_me else ""
        streak_badge = f'<span style="font-size:9px;color:var(--gold2);font-weight:600;margin-left:5px;">🔥{stk}d</span>' if stk>=3 else ""
        me_badge     = '<span style="font-size:9px;color:#3a87ab;font-weight:600;margin-left:4px;">— Saya</span>' if is_me else ""
        role_lbl     = STAFF_ROLE_MAP.get(sn,"")
        html = (
            f'<div class="card" style="{border_style}margin-bottom:7px;">'
            f'<div class="lb-row" style="border:none;padding:0;">'
            f'<div class="lb-rk">{medal}</div>'
            f'<div class="lb-av" style="background:{ac};">{ai}</div>'
            f'<div style="flex:1;min-width:0;">'
            f'<div class="lb-nm">{sn} <span style="font-size:9px;color:var(--txt);font-weight:400;">{role_lbl}</span>'
            f'{streak_badge}{me_badge}</div>'
            f'<div class="lb-sub">{tv} task</div>'
            f'<div class="lb-pbar"><div class="lb-pbar-f" style="width:{pct}%;background:{ac};"></div></div>'
            f'</div>'
            f'<div class="lb-xp">{xv:,}</div>'
            f'</div></div>'
        )
        st.markdown(html, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
#  PAGE: QUEST & STREAK
# ══════════════════════════════════════════════════════════
def page_quest_streak():
    prev_xp   = st.session_state.get("prev_xp")
    cur_lv    = _get_lvl_idx(TOTAL_XP)
    leveled_up = (
        prev_xp is not None and
        prev_xp != TOTAL_XP and
        cur_lv > _get_lvl_idx(int(prev_xp))
    )

    # Get current level index    # Get current level index
    cur_idx = _get_lvl_idx(TOTAL_XP)
    lv = LEVELS[cur_idx]
    lv_emoji = lv[1].split()[0]
    lv_name  = " ".join(lv[1].split()[1:])
    nxt_xp   = LEVELS[cur_idx+1][0] if cur_idx+1 < len(LEVELS) else 9999
    nxt_name = " ".join(LEVELS[cur_idx+1][1].split()[1:]) if cur_idx+1 < len(LEVELS) else "MAX"
    pct      = LVL_PCT

    # ── Level Path ────────────────────────────────────────────
    path_nodes = ""
    for i, (xp_t, nm) in enumerate(LEVELS):
        ico  = nm.split()[0]
        name = " ".join(nm.split()[1:])
        cls  = "pn-done" if i < cur_idx else ("pn-cur" if i == cur_idx else "pn-lock")
        path_nodes += (
            f'<div class="paw-lv-node {cls}">'
            f'<div class="paw-lv-dot">{ico}</div>'
            f'<div class="paw-lv-nm">{name}</div>'
            f'<div class="paw-lv-xp">{xp_t:,}</div>'
            f'</div>'
        )

    st.markdown(f"""
    <style>
    .paw-path-wrap{{background:#fff;border:1px solid rgba(81,161,196,.12);border-radius:12px;
      padding:16px;margin-bottom:12px;}}
    .paw-path-hd{{font-size:11px;font-weight:700;color:#b89060;text-transform:uppercase;
      letter-spacing:.8px;margin-bottom:14px;}}
    .paw-lv-path{{display:flex;align-items:flex-start;gap:0;overflow-x:auto;padding-bottom:4px;}}
    .paw-lv-node{{display:flex;flex-direction:column;align-items:center;gap:4px;flex:1;
      min-width:72px;position:relative;}}
    .paw-lv-node::after{{content:'';position:absolute;top:19px;left:50%;right:-50%;height:2px;z-index:0;}}
    .paw-lv-node:last-child::after{{display:none;}}
    .pn-done::after{{background:#51a1c4;}}
    .pn-cur::after{{background:linear-gradient(90deg,#51a1c4,rgba(81,161,196,.15));}}
    .pn-lock::after{{background:rgba(81,161,196,.1);}}
    .paw-lv-dot{{width:38px;height:38px;border-radius:99px;display:flex;align-items:center;
      justify-content:center;font-size:18px;border:2px solid transparent;z-index:1;}}
    .pn-done .paw-lv-dot{{background:#edf6fa;border-color:#51a1c4;}}
    .pn-cur .paw-lv-dot{{background:#51a1c4;border-color:#ddb551;
      box-shadow:0 0 0 4px rgba(81,161,196,.18);}}
    .pn-lock .paw-lv-dot{{background:#f4f7f8;border-color:rgba(81,161,196,.1);
      filter:grayscale(1);opacity:.4;}}
    .paw-lv-nm{{font-size:9px;font-weight:600;color:#b89060;text-align:center;line-height:1.3;}}
    .pn-cur .paw-lv-nm{{color:#3a87ab;font-weight:700;}}
    .pn-done .paw-lv-nm{{color:#2d8a4e;}}
    .paw-lv-xp{{font-size:9px;color:#b89060;font-family:'DM Mono',monospace;opacity:.7;}}
    .pn-cur .paw-lv-xp{{color:#51a1c4;opacity:1;}}
    </style>
    <div class="paw-path-wrap">
      <div class="paw-path-hd">Jalur Evolusi</div>
      <div class="paw-lv-path">{path_nodes}</div>
    </div>
    """, unsafe_allow_html=True)

    # Update prev_xp
    st.session_state["prev_xp"] = TOTAL_XP

    # ── Milestone Streak Header ────────────────────────────────
    st.markdown("---")

    # ── Milestone Streak ──────────────────────────────────────
    cm1, cm2, cm3 = st.columns(3)
    milestones = [
        (3,  "Hari Streak", "+10 XP", STREAK >= 3,  "#e8f8ee", "#2d8a4e", "rgba(45,138,78,.3)",  "&#10003; Selesai"),
        (7,  "Hari Streak", "+25 XP", STREAK >= 7,  "#edf6fa", "#3a87ab", "rgba(81,161,196,.3)",   "&#10003; Aktif"),
        (14, "Hari Streak", "+50 XP", STREAK >= 14, "#fafafa", "#b89060", "rgba(81,161,196,.1)",  f"{max(0,14-STREAK)} lagi"),
    ]
    for col, (days, title, xpl, done, bg, clr, bdr, tag) in zip([cm1, cm2, cm3], milestones):
        with col:
            st.markdown(
                f'<div style="background:{bg};border:1.5px solid {bdr};border-radius:9px;'
                f'padding:10px 13px;display:flex;align-items:center;gap:10px;">'
                f'<span style="font-size:22px;font-weight:700;font-family:var(--mono);color:{clr};width:28px;">{days}</span>'
                f'<div style="flex:1;">'
                f'<div style="font-size:12px;font-weight:600;color:{clr};">{title}</div>'
                f'<div style="font-size:10px;color:{clr};margin-top:1px;">{xpl}</div></div>'
                f'<span style="font-size:10px;font-weight:700;color:{clr};">{tag}</span></div>',
                unsafe_allow_html=True
            )

    st.markdown("---")

    # ── Quest Tabs ────────────────────────────────────────────
    tab_d, tab_w, tab_m = st.tabs(["&#128197; Daily Quest", "&#128198; Weekly Quest", "&#128467; Monthly Quest"])
    wc = (now_jkt() - timedelta(days=7)).strftime("%Y-%m-%d")
    mc = (now_jkt() - timedelta(days=30)).strftime("%Y-%m-%d")
    tt = today_task_df
    wt = user_task_df[user_task_df["Date"] >= wc] if not user_task_df.empty and "Date" in user_task_df.columns else pd.DataFrame()
    mt = user_task_df[user_task_df["Date"] >= mc] if not user_task_df.empty and "Date" in user_task_df.columns else pd.DataFrame()

    def q_html(bg, ico, nm, desc, cur, tgt_v, xp, color):
        pct2 = min(int(cur / tgt_v * 100), 100) if tgt_v > 0 else 0
        return (
            f'<div class="q-row"><div class="q-ico" style="background:{bg};">{ico}</div>'
            f'<div style="flex:1;min-width:0;"><div class="q-nm">{nm}</div><div class="q-desc">{desc}</div>'
            f'<div class="q-bar-wrap"><div class="q-bar-fill" style="width:{pct2}%;background:{color};"></div></div></div>'
            f'<div style="text-align:right;flex-shrink:0;">'
            f'<div class="q-xp" style="color:{color};">+{xp} XP{"  &#10003;" if cur >= tgt_v else ""}</div>'
            f'<div style="font-size:10px;color:var(--txt);">{pct2}%</div></div></div>'
        )

    def cnt(df, col=None, val=None):
        if df.empty: return 0
        if col and val and col in df.columns: return len(df[df[col] == val])
        return len(df)

    with tab_d:
        done_d = cnt(tt, "Status", "Done")
        inp_d  = cnt(tt)
        qcd    = cnt(
            qc_df[(qc_df["QC By"] == USER) & (qc_df["Date"] == TODAY)]
            if not qc_df.empty and "QC By" in qc_df.columns else pd.DataFrame()
        )
        urg_d  = cnt(tt, "Task Type", "Booking Urgent")
        html   = q_html("#edf6fa", "&#9989;",  "Input 5 Task",       f"{inp_d}/5 hari ini",  inp_d,  5, 50,  "#3a87ab")
        html  += q_html("var(--glt)", "&#127919;", "3 Task Done",    f"{done_d}/3 selesai",  done_d, 3, 40,  "var(--gdk)")
        html  += q_html("var(--rlt)", "&#128269;", "QC 3 Task",      f"{qcd}/3 QC hari ini", qcd,    3, 40,  "var(--red)")
        html  += q_html("var(--ylt)", "&#9889;",   "1 Booking Urgent",f"{urg_d}/1",           urg_d,  1, 60,  "var(--ydk)")
        st.markdown(f'<div class="card">{html}</div>', unsafe_allow_html=True)

    with tab_w:
        done_w = cnt(wt, "Status", "Done")
        inp_w  = cnt(wt)
        qcw    = cnt(
            qc_df[(qc_df["QC By"] == USER) & (qc_df["Date"] >= wc)]
            if not qc_df.empty and "QC By" in qc_df.columns else pd.DataFrame()
        )
        html  = q_html("#edf6fa", "&#128203;", "Input 25 Task",   f"{inp_w}/25 minggu ini", inp_w,  25, 200, "#3a87ab")
        html += q_html("var(--glt)", "&#127919;", "15 Task Done", f"{done_w}/15",           done_w, 15, 150, "var(--gdk)")
        html += q_html("var(--rlt)", "&#128269;", "QC 10 Task",   f"{qcw}/10",              qcw,    10, 150, "var(--red)")
        st.markdown(f'<div class="card">{html}</div>', unsafe_allow_html=True)

    with tab_m:
        done_m = cnt(mt, "Status", "Done")
        inp_m  = cnt(mt)
        html  = q_html("#edf6fa", "&#128203;", "Input 100 Task",  f"{inp_m}/100 bulan ini", inp_m,  100, 500, "#3a87ab")
        html += q_html("var(--glt)", "&#127919;", "60 Task Done", f"{done_m}/60",           done_m,  60, 400, "var(--gdk)")
        st.markdown(f'<div class="card">{html}</div>', unsafe_allow_html=True)


def page_dashboard():
    od  = task_df[task_df["Date"]==TODAY]["Staff"].nunique() if not task_df.empty and "Date" in task_df.columns else 0
    td  = len(task_df[task_df["Date"]==TODAY]) if not task_df.empty else 0
    xpn = len(task_df[(task_df["Status"]=="Done")&(task_df["QC Status"]=="Pending QC")]) if not task_df.empty else 0
    er = round(len(task_df[(task_df["Date"]==TODAY)&(task_df["XP"].astype(float)<0)])/max(td,1)*100,1) if not task_df.empty else 0
    st.markdown(f"""<div class="stat-row stat-row-4">
      <div class="stat-cell"><div class="stat-num" style="color:var(--green);">{od}</div><div class="stat-lbl">staff aktif</div><div class="stat-sub">dari {len(ALL_STAFF['Booker'])+len(ALL_STAFF['Finance'])}</div></div>
      <div class="stat-cell"><div class="stat-num">{td}</div><div class="stat-lbl">task hari ini</div></div>
      <div class="stat-cell"><div class="stat-num" style="color:var(--gold2);">{xpn}</div><div class="stat-lbl">XP pending QC</div></div>
      <div class="stat-cell"><div class="stat-num" style="color:var(--rose);">{er}%</div><div class="stat-lbl">error rate</div></div>
    </div>""", unsafe_allow_html=True)

    st.markdown("---")
    cl,cr = st.columns([3,2])
    with cl:
        st.markdown("#### 🖥 Session Hari Ini")
        if not session_df.empty and "Staff" in session_df.columns:
            for _,row in session_df[session_df["Date"]==TODAY].iterrows():
                sn=str(row.get("Staff","")); is_on="active" in str(row.get("Status","Active")).lower()
                av=STAFF_COLORS.get(sn,"var(--sb)"); ai=sn[:2].upper()
                tn=len(task_df[(task_df["Staff"]==sn)&(task_df["Date"]==TODAY)]) if not task_df.empty else 0
                dot_color  = "var(--gdk)" if is_on else "#c4ccd8"
                sess_class = "sess-on" if is_on else "sess-off"
                sess_label = "Online" if is_on else "Offline"
                html = (
                    f'<div class="row-card" style="margin-bottom:6px;">'
                    f'<div style="display:flex;align-items:center;gap:8px;">'
                    f'<div class="{"dot-on" if is_on else "dot-off"}"></div>'
                    f'<div style="width:22px;height:22px;border-radius:7px;background:{av};display:flex;align-items:center;justify-content:center;font-size:8px;font-weight:600;color:#fff;flex-shrink:0;">{ai}</div>'
                    f'<span style="font-size:12px;font-weight:600;color:var(--ink);flex:1;">{sn}</span>'
                    f'<span style="font-size:10px;color:var(--ink);">{tn} task</span>'
                    f'<span class="{sess_class}">{sess_label}</span>'
                    f'</div></div>'
                )
                st.markdown(html, unsafe_allow_html=True)
        else: st.info("Belum ada sesi hari ini.")

        st.markdown("#### 📁 Project Aktif")
        if not proj_df.empty:
            for _,row in proj_df.head(3).iterrows():
                nm=str(row.get("Name","")); dl=str(row.get("Deadline","")); prog=_safe_int(row.get("Progress",0))
                st.markdown(f"""<div class="row-card"><div style="font-size:12px;font-weight:600;color:var(--ink);">{nm}</div>
                <div style="font-size:9px;color:var(--txt);">Deadline: {dl}</div>
                <div class="pbar"><div class="pbar-fill" style="width:{prog}%;background:#3a87ab;"></div></div>
                <div style="font-size:9px;color:var(--txt);margin-top:2px;">{prog}%</div></div>""", unsafe_allow_html=True)

    with cr:
        st.markdown("#### ⭐ XP Pending")
        if not task_df.empty and "QC Status" in task_df.columns:
            for _,row in task_df[(task_df["Status"]=="Done")&(task_df["QC Status"]=="Pending QC")].head(5).iterrows():
                sn=str(row.get("Staff","")); ref_r=str(row.get("Ref ID","")); xp_r=_safe_int(row.get("XP",0))
                ac=STAFF_COLORS.get(sn,"var(--sb)"); ai=sn[:2].upper()
                st.markdown(f"""<div class="pend-row">
                  <div style="width:22px;height:22px;border-radius:7px;background:{ac};display:flex;align-items:center;justify-content:center;font-size:8px;font-weight:600;color:#fff;flex-shrink:0;">{ai}</div>
                  <div style="flex:1;min-width:0;"><div style="font-size:11px;font-weight:600;color:var(--ink);">{sn}</div><div style="font-size:9px;color:var(--txt);">{ref_r}</div></div>
                  <span style="font-size:11px;font-weight:600;color:#3a87ab;font-family:var(--mono);">+{xp_r}</span>
                </div>""", unsafe_allow_html=True)

        st.markdown("#### 📊 Performa Tim Hari Ini")
        if not task_df.empty and "Staff" in task_df.columns:
            tp = task_df[task_df["Date"]==TODAY].groupby("Staff")["XP"].sum().sort_values(ascending=False)
            mx = int(tp.max()) if not tp.empty else 1
            for sn,xpv in tp.head(8).items():
                if sn=="Manager": continue
                ac=STAFF_COLORS.get(sn,"var(--sb)"); ai=sn[:2].upper(); pct=int(int(xpv)/mx*100) if mx>0 else 0
                st.markdown(f"""<div style="display:flex;align-items:center;gap:7px;margin-bottom:6px;">
                  <div style="width:20px;height:20px;border-radius:7px;background:{ac};display:flex;align-items:center;justify-content:center;font-size:7px;font-weight:600;color:#fff;flex-shrink:0;">{ai}</div>
                  <div style="flex:1;min-width:0;"><div style="display:flex;justify-content:space-between;margin-bottom:2px;">
                    <span style="font-size:11px;font-weight:600;color:var(--ink);">{sn}</span>
                    <span style="font-size:10px;font-weight:600;color:#3a87ab;font-family:var(--mono);">+{int(xpv)}</span></div>
                    <div class="pbar"><div class="pbar-fill" style="width:{pct}%;background:{ac};"></div></div>
                  </div></div>""", unsafe_allow_html=True)

def page_session_monitor():
    on_n=session_df[session_df["Date"]==TODAY]["Staff"].nunique() if not session_df.empty and "Date" in session_df.columns else 0
    ts=len(ALL_STAFF["Booker"])+len(ALL_STAFF["Finance"])
    avg_dur=0
    if not session_df.empty and "Duration Minutes" in session_df.columns:
        td_s=session_df[session_df["Date"]==TODAY]
        avg_dur = int(td_s["Duration Minutes"].astype(float).mean()) if not td_s.empty else 0
    h,m=divmod(avg_dur,60)
    tt=len(task_df[task_df["Date"]==TODAY]) if not task_df.empty and "Date" in task_df.columns else 0
    st.markdown(f"""<div class="stat-row stat-row-4">
      <div class="stat-cell"><div class="stat-num" style="color:var(--green);">{on_n}</div><div class="stat-lbl">login hari ini</div></div>
      <div class="stat-cell"><div class="stat-num" style="color:var(--rose);">{max(0,ts-on_n)}</div><div class="stat-lbl">belum login</div></div>
      <div class="stat-cell"><div class="stat-num">{h}j {m}m</div><div class="stat-lbl">rata-rata durasi</div></div>
      <div class="stat-cell"><div class="stat-num">{tt}</div><div class="stat-lbl">total task</div></div>
    </div>""", unsafe_allow_html=True)

    st.markdown("---")
    if session_df.empty or "Staff" not in session_df.columns: st.info("Belum ada data sesi."); return
    fd=st.selectbox("Filter",["Hari Ini","7 Hari","Semua"],key="sm_f")
    disp=session_df.copy()
    if fd=="Hari Ini": disp=disp[disp["Date"]==TODAY]
    elif fd=="7 Hari": disp=disp[disp["Date"]>=(now_jkt()-timedelta(days=7)).strftime("%Y-%m-%d")]
    for _,row in disp.sort_values("Date",ascending=False).head(50).iterrows():
        sn=str(row.get("Staff","")); rn=str(row.get("Role",""))
        lt=str(row.get("Login Time",""))[:16]; dur=_safe_int(row.get("Duration Minutes",0))
        is_on="active" in str(row.get("Status","Active")).lower()
        ac=STAFF_COLORS.get(sn,"var(--sb)"); ai=sn[:2].upper()
        ai_t=classify_ai(task_df,sn)
        ai_c={"Pro":"var(--gdk)","Balanced":"#3a87ab","Slow":"var(--ydk)","Risky":"var(--red)"}.get(ai_t,"#3a87ab")
        # FIX: row.get("Date", TODAY) → str(row.get("Date",""))
        row_date = str(row.get("Date","")) or TODAY
        tn=len(task_df[(task_df["Staff"]==sn)&(task_df["Date"]==row_date)]) if not task_df.empty else 0
        dot_col2   = "var(--gdk)" if is_on else "#c4ccd8"
        sess_cls2  = "sess-on" if is_on else "sess-off"
        sess_lbl2  = "Online" if is_on else "Offline"
        html = (
            f'<div class="card" style="margin-bottom:7px;">'
            f'<div style="display:flex;align-items:center;gap:8px;">'
            f'<div class="{"dot-on" if is_on else "dot-off"}"></div>'
            f'<div style="width:24px;height:24px;border-radius:7px;background:{ac};display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:600;color:#fff;flex-shrink:0;">{ai}</div>'
            f'<span style="font-size:12px;font-weight:600;color:var(--ink);flex:1;">{sn}</span>'
            f'<span style="font-size:9px;color:var(--txt);">{rn}</span>'
            f'<span style="font-size:10px;color:var(--txt);font-family:var(--mono);">{lt}</span>'
            f'<span style="font-size:10px;font-weight:600;color:var(--ink);font-family:var(--mono);">{dur}m</span>'
            f'<span style="font-size:11px;color:var(--ink);">{tn} task</span>'
            f'<span style="font-size:9px;font-weight:600;color:{ai_c};">{ai_t}</span>'
            f'<span class="{sess_cls2}">{sess_lbl2}</span>'
            f'</div></div>'
        )
        st.markdown(html, unsafe_allow_html=True)

def page_semua_task():
    if task_df.empty: st.info("Belum ada task."); return
    cf1,cf2,cf3=st.columns(3)
    with cf1: fs=st.selectbox("Staff",["Semua"]+ALL_STAFF_FLAT[1:],key="at_fs")
    with cf2: ft=st.selectbox("Status",["Semua"]+STATUS_LIST,key="at_ft")
    with cf3: fp=st.selectbox("Periode",["Hari Ini","7 Hari","30 Hari","Semua"],key="at_fp")
    disp=task_df.copy()
    if fs!="Semua" and "Staff" in disp.columns: disp=disp[disp["Staff"]==fs]
    if ft!="Semua" and "Status" in disp.columns: disp=disp[disp["Status"]==ft]
    if fp=="Hari Ini": disp=disp[disp["Date"]==TODAY]
    elif fp=="7 Hari": disp=disp[disp["Date"]>=(now_jkt()-timedelta(days=7)).strftime("%Y-%m-%d")]
    elif fp=="30 Hari": disp=disp[disp["Date"]>=(now_jkt()-timedelta(days=30)).strftime("%Y-%m-%d")]
    disp=disp.sort_values("Timestamp",ascending=False)
    st.markdown(f"**{len(disp)} task**")
    for idx,row in disp.head(50).iterrows():
        sn=str(row.get("Staff","")); tr=str(row.get("Task Type",""))
        ref_r=str(row.get("Ref ID","")); sr=str(row.get("Status",""))
        xp_r=_safe_int(row.get("XP",0)); hr=str(row.get("Hotel",""))
        ac=STAFF_COLORS.get(sn,"var(--sb)"); ai=sn[:2].upper()
        with st.expander(f"{tr} — {hr or sn}  ·  {ref_r}  [{sr}]"):
            mc1,mc2=st.columns([3,1])
            with mc1:
                with st.form(f"mgr_edit_{ref_r}_{idx}"):
                    me1,me2=st.columns(2)
                    with me1:
                        new_type = st.selectbox("Jenis Task",TASK_TYPE_LIST,index=TASK_TYPE_LIST.index(tr) if tr in TASK_TYPE_LIST else 0)
                        new_hotel= st.text_input("Hotel",value=hr)
                    with me2:
                        new_sts  = st.selectbox("Status",STATUS_LIST,index=STATUS_LIST.index(sr) if sr in STATUS_LIST else 0)
                        new_notes= st.text_input("Notes",value=str(row.get("Notes","")))
                    btn_upd=st.form_submit_button("💾 Update",use_container_width=True)
                if btn_upd:
                    row_idx=find_row_by_ref(ref_r)
                    if row_idx:
                        ok,err=ws_batch_update("Task Log",row_idx,{"D":new_type,"F":new_hotel,"H":new_notes,"I":new_sts,"R":now_str()})
                        if ok:
                            load_data.clear(); st.session_state.toast_msg=f"Task **{ref_r}** diupdate."; st.rerun()
                        else: st.error(f"Gagal: {err}")
                    else: st.error("Ref ID tidak ditemukan.")
            with mc2:
                st.markdown(f"""<div style="text-align:center;padding:12px;background:var(--sb);border-radius:10px;">
                  <div style="font-size:9px;color:rgba(255,255,255,.4);margin-bottom:5px;">XP</div>
                  <div style="font-size:22px;font-weight:700;color:#51a1c4;font-family:var(--mono);">{xp_r:+}</div>
                  <div style="width:24px;height:24px;border-radius:7px;background:{ac};display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:600;color:#fff;margin:8px auto 3px;">{ai}</div>
                  <div style="font-size:11px;color:rgba(255,255,255,.7);">{sn}</div>
                </div>""", unsafe_allow_html=True)

def page_xp_control():
    # ── Stat strip ──────────────────────────────────────────
    wa_list = get_pending_holiday_allowance(xplog_df)
    n_task  = len(task_df[(task_df["Status"]=="Done")&(task_df["QC Status"]=="Pending QC")]) if not task_df.empty and "QC Status" in task_df.columns else 0
    n_wa    = len(wa_list)
    n_app   = len(xplog_df[xplog_df["Applied By"]==USER]) if not xplog_df.empty and "Applied By" in xplog_df.columns else 0
    st.markdown(f"""<div class="stat-row stat-row-3">
      <div class="stat-cell"><div class="stat-num" style="color:var(--rose);">{n_task}</div>
        <div class="stat-lbl">XP task pending</div></div>
      <div class="stat-cell"><div class="stat-num" style="color:#3a87ab;">{n_wa}</div>
        <div class="stat-lbl">allowance pending</div></div>
      <div class="stat-cell"><div class="stat-num" style="color:var(--blue2);">{n_app}</div>
        <div class="stat-lbl">approved oleh kamu</div></div>
    </div>""", unsafe_allow_html=True)

    cl, cr = st.columns([3, 2])

    with cl:
        # ── XP Task Pending ──────────────────────────────────
        st.markdown("#### ⭐ XP Task Pending Approval")
        if not task_df.empty and "QC Status" in task_df.columns:
            pending = task_df[(task_df["Status"]=="Done")&(task_df["QC Status"]=="Pending QC")]
            if pending.empty: st.info("Tidak ada XP task pending. 🎉")
            for idx, row in pending.head(20).iterrows():
                sn    = str(row.get("Staff","")); ref_r = str(row.get("Ref ID",""))
                task_r= str(row.get("Task Type","")); xp_r = _safe_int(row.get("XP",0))
                d_r   = str(row.get("Date",""))
                hb    = calc_holiday_bonus(d_r)
                extra = f" 🎁 +{hb['xp']} {hb['label']}" if hb else ""
                with st.expander(f"{sn} — {task_r}  ·  +{xp_r} XP{extra}"):
                    if hb:
                        st.markdown(
                            f'<div style="background:{hb["color"]}11;border:1px solid {hb["color"]}33;'
                            f'border-radius:7px;padding:8px 11px;margin-bottom:8px;font-size:11px;'
                            f'color:{hb["color"]};">🎁 <strong>{hb["label"]} Allowance</strong> '
                            f'+{hb["xp"]} XP akan dicatat ke XP Log setelah di-approve.</div>',
                            unsafe_allow_html=True)
                    b1,b2,b3 = st.columns(3)
                    with b1:
                        if st.button("✅ Approve",key=f"app_{ref_r}_{idx}",use_container_width=True):
                            ri = find_row_by_ref(ref_r)
                            if ri: ws_batch_update("Task Log",ri,{"M":"OK"})
                            load_data.clear(); st.session_state.toast_msg=f"Approved **{ref_r}**."; st.rerun()
                    with b2:
                        if st.button("⏸ Hold",key=f"hold_{ref_r}_{idx}",use_container_width=True):
                            st.session_state.toast_msg=f"**{ref_r}** di-hold."; st.session_state.toast_type="warning"; st.rerun()
                    with b3:
                        if st.button("❌ Penalti",key=f"pen_{ref_r}_{idx}",use_container_width=True):
                            ri = find_row_by_ref(ref_r)
                            if ri: ws_batch_update("Task Log",ri,{"M":"Ada Isu"})
                            load_data.clear(); st.session_state.toast_msg=f"Penalti **{ref_r}**."; st.session_state.toast_type="error"; st.rerun()

        # ── Weekend & Holiday Allowance Pending ──────────────
        st.markdown("---")
        st.markdown("#### 🎁 Weekend & Holiday Allowance Pending")
        if not wa_list:
            st.info("Tidak ada Weekend Allowance pending.")
        else:
            for wi, wa in enumerate(wa_list):
                sn_wa  = wa["staff"]; amt_wa = wa["amount"]
                rsn_wa = wa["reason"]; ts_wa  = wa["ts"][:16]
                av_c   = STAFF_COLORS.get(sn_wa,"var(--sb)")
                av_i   = sn_wa[:2].upper()
                hcol   = "#dc2626" if "Merah" in rsn_wa else "#d97706" if "Minggu" in rsn_wa else "#3a87ab"
                hlbl   = "Tanggal Merah" if "Merah" in rsn_wa else "Minggu" if "Minggu" in rsn_wa else "Sabtu"
                st.markdown(
                    f'<div style="background:#fff;border:1.5px solid {hcol}33;border-radius:10px;'
                    f'padding:12px 14px;margin-bottom:8px;">'
                    f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:9px;">'
                    f'<div style="width:32px;height:32px;border-radius:9px;background:{av_c};'
                    f'display:flex;align-items:center;justify-content:center;font-size:11px;'
                    f'font-weight:700;color:#fff;flex-shrink:0;">{av_i}</div>'
                    f'<div style="flex:1;min-width:0;">'
                    f'<div style="font-size:13px;font-weight:600;color:var(--ink);">{sn_wa}</div>'
                    f'<div style="font-size:11px;color:#b89060;">{rsn_wa}</div></div>'
                    f'<div style="text-align:right;flex-shrink:0;">'
                    f'<div style="font-size:18px;font-weight:700;font-family:var(--mono);color:{hcol};">'
                    f'+{amt_wa} XP</div>'
                    f'<span style="font-size:9px;font-weight:700;padding:1px 7px;border-radius:99px;'
                    f'background:{hcol}15;color:{hcol};border:1px solid {hcol}33;">🎁 {hlbl}</span></div></div>'
                    f'<div style="font-size:10px;color:#b89060;margin-bottom:8px;">📅 {ts_wa}</div></div>',
                    unsafe_allow_html=True)
                wc1, wc2 = st.columns(2)
                with wc1:
                    if st.button(f"✅ Setujui +{amt_wa} XP", key=f"wa_ok_{wi}", use_container_width=True):
                        try:
                            wb_ = get_cached_wb(); ws_ = wb_.worksheet("XP Log")
                            rows_ = ws_.get_all_values()
                            for ri_, r_ in enumerate(rows_):
                                if (len(r_)>=6 and r_[1]==sn_wa and
                                    r_[2]=="Weekend Allowance" and
                                    r_[5]=="PENDING" and r_[4]==rsn_wa):
                                    ws_.update_cell(ri_+1,6,USER); break
                        except Exception: pass
                        load_data.clear()
                        st.session_state.toast_msg = f"🎁 +{amt_wa} XP Weekend Allowance untuk **{sn_wa}** disetujui."
                        st.rerun()
                with wc2:
                    if st.button("❌ Tolak", key=f"wa_no_{wi}", use_container_width=True):
                        try:
                            wb_ = get_cached_wb(); ws_ = wb_.worksheet("XP Log")
                            rows_ = ws_.get_all_values()
                            for ri_, r_ in enumerate(rows_):
                                if (len(r_)>=6 and r_[1]==sn_wa and
                                    r_[2]=="Weekend Allowance" and
                                    r_[5]=="PENDING" and r_[4]==rsn_wa):
                                    ws_.update_cell(ri_+1,6,"REJECTED"); break
                        except Exception: pass
                        load_data.clear()
                        st.session_state.toast_msg = f"Weekend Allowance **{sn_wa}** ditolak."
                        st.session_state.toast_type = "warning"; st.rerun()

    with cr:
        # ── Weekend Summary ──────────────────────────────────
        st.markdown("#### 📊 Ringkasan Weekend Ini")
        ws_sum = get_weekend_summary(task_df)
        if not ws_sum:
            st.info("Belum ada aktivitas weekend minggu ini.")
        else:
            for sn_s, data_s in ws_sum.items():
                av_c = STAFF_COLORS.get(sn_s,"var(--sb)")
                av_i = sn_s[:2].upper()
                st.markdown(
                    f'<div style="background:#fff;border:1px solid rgba(81,161,196,.12);'
                    f'border-radius:9px;padding:9px 12px;margin-bottom:5px;'
                    f'display:flex;align-items:center;gap:9px;">'
                    f'<div style="width:24px;height:24px;border-radius:7px;background:{av_c};'
                    f'display:flex;align-items:center;justify-content:center;font-size:9px;'
                    f'font-weight:700;color:#fff;flex-shrink:0;">{av_i}</div>'
                    f'<div style="flex:1;min-width:0;">'
                    f'<div style="font-size:12px;font-weight:600;color:var(--ink);">{sn_s}</div>'
                    f'<div style="font-size:10px;color:#b89060;">{data_s["tasks"]} task weekend</div></div>'
                    f'<div style="font-size:13px;font-weight:700;font-family:var(--mono);'
                    f'color:#3a87ab;">+{data_s["bonus_xp"]} XP</div></div>',
                    unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("#### ✏️ Bonus / Penalti Manual")
        with st.form("manual_xp_form"):
            tgt  = st.selectbox("Staff", ALL_STAFF_FLAT[1:])
            xtyp = st.selectbox("Jenis", [
                "Bonus XP Manual","Penalti XP","Hold XP",
                "Weekend Allowance Manual","Holiday Allowance Manual"])
            amt  = st.number_input("Jumlah XP", 1, 500, 25)
            rsn  = st.text_input("Alasan")
            sub  = st.form_submit_button("Terapkan", use_container_width=True)
        if sub:
            sign = -1 if "Penalti" in xtyp else 1
            ws_append("XP Log",[now_str(),tgt,xtyp,sign*amt,rsn,USER])
            load_data.clear()
            st.session_state.toast_msg = f"{'Bonus' if sign>0 else 'Penalti'} {amt} XP → **{tgt}**."
            st.rerun()
def page_kelola_project():
    cl,cr=st.columns([3,2])
    with cl:
        st.markdown("#### 📁 Project Aktif")
        if proj_df.empty: st.info("Belum ada project.")
        else:
            for _,row in proj_df.iterrows():
                nm=str(row.get("Name","")); dl=str(row.get("Deadline",""))
                prog=_safe_int(row.get("Progress",0)); cat=str(row.get("Category",""))
                sl=[s.strip() for s in str(row.get("Staff","")).split(",") if s.strip()]
                pc="var(--gdk)" if prog>=80 else "#3a87ab" if prog>=50 else "var(--ydk)"
                st.markdown(f"""<div class="row-card">
                  <div style="display:flex;justify-content:space-between;margin-bottom:5px;">
                    <div><div style="font-size:12px;font-weight:600;color:var(--ink);">{nm}</div>
                    <div style="font-size:9px;color:var(--txt);">{cat} · Deadline {dl}</div></div>
                    <span style="font-size:13px;font-weight:700;color:var(--gold2);font-family:var(--mono);">{prog}%</span></div>
                  <div style="display:flex;gap:3px;margin-bottom:5px;">
                    {"".join([f'<div style="width:18px;height:18px;border-radius:7px;background:{STAFF_COLORS.get(s,"var(--sb)")};display:flex;align-items:center;justify-content:center;font-size:7px;font-weight:600;color:#fff;border:1.5px solid #fff;">{s[:2].upper()}</div>' for s in sl])}
                  </div>
                  <div class="pbar"><div class="pbar-fill" style="width:{prog}%;background:{pc};"></div></div>
                </div>""", unsafe_allow_html=True)
    with cr:
        st.markdown("#### ➕ Buat Project Baru")
        with st.form("new_project_form"):
            pnm =st.text_input("Nama Project")
            pcat=st.selectbox("Kategori",["Booking Hotel","Finance & Payment","QC & Validasi","Event Khusus"])
            pdl =st.date_input("Deadline")
            pxp =st.number_input("Target XP Tim",100,9999,500,50)
            pstf=st.multiselect("Tugaskan ke Staff",ALL_STAFF_FLAT[1:])
            psub=st.form_submit_button("Buat Project",use_container_width=True)
        if psub:
            if not pnm.strip(): st.error("Nama project wajib diisi.")
            else:
                ok,err=ws_append("Projects",[f"PRJ-{str(uuid.uuid4())[:6].upper()}",pnm.strip(),pcat,str(pdl),",".join(pstf),pxp,0,"Active",now_str()])
                if ok: load_data.clear(); st.session_state.toast_msg=f"Project **{pnm}** dibuat."; st.rerun()
                else:  st.error(f"Gagal: {err}")

def page_performa_tim():
    if task_df.empty or "Staff" not in task_df.columns: st.info("Belum ada data."); return
    perf=task_df[task_df["Staff"]!="Manager"].groupby("Staff").agg(
        XP=("XP","sum"),Total=("Ref ID","count"),Done=("Status",lambda x:(x=="Done").sum())
    ).reset_index()
    perf["Done Rate"]=(perf["Done"]/perf["Total"].clip(1)*100).round(1)
    perf=perf.sort_values("XP",ascending=False)
    mx=int(perf["XP"].max()) if not perf.empty else 1
    for _,row in perf.iterrows():
        sn=row["Staff"]; xv=int(row["XP"]); dv=int(row["Done"]); tv=int(row["Total"]); dr=float(row["Done Rate"])
        ac=STAFF_COLORS.get(sn,"var(--sb)"); ai=sn[:2].upper()
        pct=int(xv/mx*100) if mx>0 else 0
        lvl_n,_,_,_,_=get_level(xv); stk=streak_days(task_df,sn)
        role_lbl = STAFF_ROLE_MAP.get(sn,"")
        streak_badge = f'<span style="font-size:9px;color:var(--gold2);font-weight:600;margin-left:5px;">🔥{stk}d</span>' if stk>=3 else ""
        html = (
            f'<div class="card" style="margin-bottom:8px;">'
            f'<div style="display:flex;align-items:center;gap:10px;">'
            f'<div style="width:36px;height:36px;border-radius:7px;background:{ac};display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:600;color:#fff;flex-shrink:0;">{ai}</div>'
            f'<div style="flex:1;min-width:0;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px;">'
            f'<span style="font-size:13px;font-weight:600;color:var(--ink);">{sn} '
            f'<span style="font-size:9px;color:var(--txt);font-weight:400;">{role_lbl} · {lvl_n}</span>'
            f'{streak_badge}</span>'
            f'<span style="font-size:13px;font-weight:700;color:#3a87ab;font-family:var(--mono);">{xv:,} XP</span>'
            f'</div>'
            f'<div class="pbar"><div class="pbar-fill" style="width:{pct}%;background:{ac};"></div></div>'
            f'<div style="display:flex;gap:12px;margin-top:4px;font-size:10px;color:var(--txt);">'
            f'<span>{tv} task total</span><span>{dv} done</span>'
            f'<span style="color:var(--blue2);font-weight:600;">{dr}% done rate</span>'
            f'</div></div></div></div>'
        )
        st.markdown(html, unsafe_allow_html=True)

def page_activity_log():
    if task_df.empty: st.info("Belum ada aktivitas."); return
    fs=st.selectbox("Filter Staff",["Semua"]+ALL_STAFF_FLAT[1:],key="alog_fs")
    disp=task_df.copy()
    if fs!="Semua" and "Staff" in disp.columns: disp=disp[disp["Staff"]==fs]
    for _,row in disp.sort_values("Timestamp",ascending=False).head(100).iterrows():
        sn=str(row.get("Staff","")); tr=str(row.get("Task Type",""))
        sr=str(row.get("Status","")); ts=str(row.get("Timestamp",""))[:16]
        ref_r=str(row.get("Ref ID","")); xp_r=_safe_int(row.get("XP",0))
        ac=STAFF_COLORS.get(sn,"var(--sb)"); ai=sn[:2].upper()
        st.markdown(f"""<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--bdr2);">
          <div style="width:22px;height:22px;border-radius:7px;background:{ac};display:flex;align-items:center;justify-content:center;font-size:8px;font-weight:600;color:#fff;flex-shrink:0;">{ai}</div>
          <span style="font-size:11px;font-weight:600;color:var(--ink);">{sn}</span>
          <span style="font-size:10px;color:var(--txt);">{tr}</span>
          <span class="mtag">{ref_r}</span>
          {status_html(sr)}
          <span style="font-size:10px;font-weight:600;color:#3a87ab;font-family:var(--mono);">{xp_r:+}</span>
          <span style="font-size:9px;color:var(--txt);margin-left:auto;">{ts}</span>
        </div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
#  ROUTING
# ══════════════════════════════════════════════════════════
PAGE = st.session_state.nav_page
routes_mgr = {"Dashboard":page_dashboard,"Session Monitor":page_session_monitor,
               "Semua Task":page_semua_task,"XP Control":page_xp_control,
               "Kelola Project":page_kelola_project,"Performa Tim":page_performa_tim,
               "Activity Log":page_activity_log}
routes_staff = {"My Tasks":page_my_tasks,"QC Antrian":page_qc_antrian,
                "Status QC Saya":page_status_qc,"Leaderboard":page_leaderboard,
                "Quest & Streak":page_quest_streak}
routes = routes_mgr if ROLE=="Manager" else routes_staff
fn = routes.get(PAGE, page_dashboard if ROLE=="Manager" else page_my_tasks)
fn()

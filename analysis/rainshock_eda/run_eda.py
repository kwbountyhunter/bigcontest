import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'analysis' / 'rainshock_eda'
OUT.mkdir(parents=True, exist_ok=True)

CARD1 = ROOT / 'data' / '신한카드_데이터' / '신한카드_빅콘테스트2026_데이터1.txt'
AWS400 = ROOT / 'data' / 'public_rainshock' / 'raw' / 'kma' / 'aws_hourly' / 'stn_400' / 'OBS_AWS_TIM_20261005094738.csv'
ASOS_BASE = ROOT / 'data' / 'public_rainshock' / 'raw' / 'kma' / 'asos_hourly'
HOLIDAY = ROOT / 'data' / 'public_rainshock' / 'raw' / 'kasi' / 'holidays' / '2025' / '20261005T002238Z' / 'kasi_holidays_2025.raw.json'

TIME_BAND_ORDER = ['00_05','06_11','12_17','18_23']
TIME_BAND_HOURS = {
    '00_05': list(range(0,6)),
    '06_11': list(range(6,12)),
    '12_17': list(range(12,18)),
    '18_23': list(range(18,24)),
}


def safe_div(a,b):
    return np.where((b!=0)&(~pd.isna(b)), a/b, np.nan)


def winsor(s, lo=0.01, hi=0.99):
    qlo, qhi = s.quantile([lo, hi])
    return s.clip(qlo, qhi)


def mean_or_nan(values):
    arr=np.array(values, dtype='float64')
    arr=arr[~np.isnan(arr)]
    return float(arr.mean()) if len(arr) else np.nan


def records(df):
    return json.loads(df.to_json(orient='records', force_ascii=False))


def parse_asos_station(stn):
    rows=[]
    for f in sorted((ASOS_BASE / f'stn_{stn}').glob('*/asos_hourly_stn_*_2025*.raw.json')):
        text=f.read_text(encoding='utf-8')
        data=json.loads(text)
        if data['response']['header'].get('resultCode')!='00':
            continue
        items=data['response']['body']['items']['item']
        if isinstance(items, dict):
            items=[items]
        rows.extend(items)
    df=pd.DataFrame(rows)
    if df.empty:
        return df
    df['tm']=pd.to_datetime(df['tm'])
    for col in ['rn','ta','hm','ws']:
        if col in df.columns:
            df[col]=pd.to_numeric(df[col].replace('', np.nan), errors='coerce')
    df['station_id']=str(stn)
    return df


def aggregate_weather_hourly(hourly, region):
    h=hourly.copy()
    h['date']=h['tm'].dt.date.astype(str)
    h['hour']=h['tm'].dt.hour
    h['rn0']=h['rn'].fillna(0)
    h['rain_positive_hour']=(h['rn0']>0).astype(int)
    daily=h.groupby('date').agg(
        daily_rain_mm=('rn0','sum'),
        max_hourly_rain_mm=('rn0','max'),
        rain_hours=('rain_positive_hour','sum'),
        temp_mean_c=('ta','mean'),
        humidity_mean_pct=('hm','mean'),
        wind_mean_ms=('ws','mean'),
        hourly_obs=('tm','count'),
    ).reset_index()
    six=h.copy()
    six['TIME_GB']=pd.cut(six['hour'], bins=[-1,5,11,17,23], labels=TIME_BAND_ORDER)
    six=six.groupby(['date','TIME_GB'], observed=False).agg(
        rain_6h_mm=('rn0','sum'),
        max_hourly_rain_6h_mm=('rn0','max'),
        rain_hours_6h=('rain_positive_hour','sum'),
        obs_6h=('tm','count'),
    ).reset_index()
    daily['region']=region
    six['region']=region
    return daily, six

# Weather: Gangnam AWS400
aws=pd.read_csv(AWS400, encoding='cp949')
aws=aws.rename(columns={'일시':'tm','강수량(mm)':'rn','기온(°C)':'ta','습도(%)':'hm','풍속(m/s)':'ws'})
aws['tm']=pd.to_datetime(aws['tm'])
for col in ['rn','ta','hm','ws']:
    aws[col]=pd.to_numeric(aws[col], errors='coerce')
weather_gn_daily, weather_gn_6h=aggregate_weather_hourly(aws, '서울 강남구')

# Weather: Chuncheon ASOS101 primary, North Chuncheon retained for QA
asos101=parse_asos_station('101')
asos93=parse_asos_station('93')
weather_cc_daily, weather_cc_6h=aggregate_weather_hourly(asos101, '강원 춘천시')
weather_93_daily, _=aggregate_weather_hourly(asos93, '강원 춘천시_북춘천')

weather_daily=pd.concat([weather_gn_daily, weather_cc_daily], ignore_index=True)
weather_6h=pd.concat([weather_gn_6h, weather_cc_6h], ignore_index=True)
weather_daily['date']=pd.to_datetime(weather_daily['date'])
weather_6h['date']=pd.to_datetime(weather_6h['date'])
weather_daily.to_csv(OUT/'weather_daily_summary.csv', index=False, encoding='utf-8-sig')
weather_6h.to_csv(OUT/'weather_6h_summary.csv', index=False, encoding='utf-8-sig')

# Holidays
with open(HOLIDAY, encoding='utf-8') as fh:
    hjson=json.load(fh)
items=hjson['response']['body']['items']['item']
holidays=pd.DataFrame(items)
holidays['date']=pd.to_datetime(holidays['locdate'].astype(str))
holiday_dates=set(holidays.loc[holidays['isHoliday']=='Y','date'])

# Card data daily + 6h
usecols=('TA_YMD','TIME_GB','MCT_SGG_CD','MCT_RY_CD','TS_AT','USE_CNT')
card=pd.read_csv(CARD1, sep='\t', encoding='cp949')
card=card.loc[:, list(usecols)]
card['date']=pd.to_datetime(card['TA_YMD'].astype(str))
card['TS_AT']=pd.to_numeric(card['TS_AT'], errors='coerce')
card['USE_CNT']=pd.to_numeric(card['USE_CNT'], errors='coerce')
card['dow']=card['date'].dt.dayofweek
card['is_weekend']=card['dow'].isin([5,6]).astype(int)
card['is_holiday']=card['date'].isin(holiday_dates).astype(int)

daily=card.groupby(['date','MCT_SGG_CD','MCT_RY_CD']).agg(sales=('TS_AT','sum'), txn=('USE_CNT','sum')).reset_index()
daily['dow']=daily['date'].dt.dayofweek
baseline=daily.groupby(['MCT_SGG_CD','MCT_RY_CD','dow']).agg(base_sales=('sales','median'), base_txn=('txn','median')).reset_index()
daily=daily.merge(baseline, on=['MCT_SGG_CD','MCT_RY_CD','dow'], how='left')
daily['sales_idx']=safe_div(daily['sales'], daily['base_sales'])
daily['txn_idx']=safe_div(daily['txn'], daily['base_txn'])
daily['sales_dev_pct']=(daily['sales_idx']-1)*100
daily['txn_dev_pct']=(daily['txn_idx']-1)*100
joined=daily.merge(weather_daily, left_on=['date','MCT_SGG_CD'], right_on=['date','region'], how='left')
joined['rain_bin']=pd.cut(joined['daily_rain_mm'].fillna(0), [-0.001,0,5,20,50,999], labels=['0','0-5','5-20','20-50','50+'])
joined.to_csv(OUT/'daily_region_industry_weather_join.csv', index=False, encoding='utf-8-sig')

# Daily correlation by region/industry
corr_rows=[]
for (region, industry), g in joined.dropna(subset=['daily_rain_mm','sales_dev_pct']).groupby(['MCT_SGG_CD','MCT_RY_CD']):
    if len(g)>=30 and g['daily_rain_mm'].nunique()>1:
        pear=g['daily_rain_mm'].corr(g['sales_dev_pct'], method='pearson')
        spear=g['daily_rain_mm'].corr(g['sales_dev_pct'], method='spearman')
        heavy=g[g['daily_rain_mm']>=20]
        dry=g[g['daily_rain_mm']==0]
        corr_rows.append({
            'region':region,'industry':industry,'n_days':len(g),'rain_days':int((g['daily_rain_mm']>0).sum()),'heavy20_days':len(heavy),
            'pearson_rain_sales_dev':pear,'spearman_rain_sales_dev':spear,
            'mean_sales_dev_dry':dry['sales_dev_pct'].mean() if len(dry) else np.nan,
            'mean_sales_dev_heavy20':heavy['sales_dev_pct'].mean() if len(heavy) else np.nan,
            'heavy20_minus_dry_pp':(heavy['sales_dev_pct'].mean()-dry['sales_dev_pct'].mean()) if len(heavy) and len(dry) else np.nan,
            'median_sales_dev_dry':dry['sales_dev_pct'].median() if len(dry) else np.nan,
            'median_sales_dev_heavy20':heavy['sales_dev_pct'].median() if len(heavy) else np.nan,
            'median_heavy20_minus_dry_pp':(heavy['sales_dev_pct'].median()-dry['sales_dev_pct'].median()) if len(heavy) and len(dry) else np.nan,
            'mean_txn_dev_heavy20':heavy['txn_dev_pct'].mean() if len(heavy) else np.nan,
        })
corr=pd.DataFrame(corr_rows).sort_values(['median_heavy20_minus_dry_pp','spearman_rain_sales_dev'])
corr.to_csv(OUT/'industry_rain_correlation_rank.csv', index=False, encoding='utf-8-sig')

# Rain bin summary by region
rain_bin_summary=joined.groupby(['MCT_SGG_CD','rain_bin'], observed=False).agg(
    rows=('sales_dev_pct','count'),
    industries=('MCT_RY_CD','nunique'),
    mean_sales_dev_pct=('sales_dev_pct','mean'),
    median_sales_dev_pct=('sales_dev_pct','median'),
    mean_txn_dev_pct=('txn_dev_pct','mean')
).reset_index()
rain_bin_summary.to_csv(OUT/'rain_bin_sales_response_by_region.csv', index=False, encoding='utf-8-sig')

# Event/rebound summary for events based on daily rain >= 20mm
series=[]
for region, wg in weather_daily.sort_values('date').groupby('region'):
    wg=wg.reset_index(drop=True)
    in_event=False; event_id=0
    for i,row in wg.iterrows():
        if row['daily_rain_mm']>=20 and not in_event:
            event_id+=1; in_event=True
        elif row['daily_rain_mm']<20:
            in_event=False
        if row['daily_rain_mm']>=20:
            series.append({'region':region,'event_id':event_id,'event_date':row['date'],'rain_mm':row['daily_rain_mm']})
events=pd.DataFrame(series)
event_rows=[]
if not events.empty:
    for _, ev in events.iterrows():
        region=ev['region']; d=ev['event_date']
        for industry, g in joined[joined['MCT_SGG_CD']==region].groupby('MCT_RY_CD'):
            window=g[(g['date']>=d-pd.Timedelta(days=3)) & (g['date']<=d+pd.Timedelta(days=3))].copy()
            if window.empty: continue
            vals={int((r['date']-d).days): r['sales_dev_pct'] for _,r in window.iterrows()}
            pre=mean_or_nan([vals.get(-3,np.nan), vals.get(-2,np.nan), vals.get(-1,np.nan)])
            d0=vals.get(0,np.nan)
            post=mean_or_nan([vals.get(1,np.nan), vals.get(2,np.nan), vals.get(3,np.nan)])
            event_rows.append({'region':region,'industry':industry,'event_date':d,'rain_mm':ev['rain_mm'],'pre3_sales_dev_pct':pre,'d0_sales_dev_pct':d0,'post3_sales_dev_pct':post,'rebound_gap_pp':post-d0 if pd.notna(post) and pd.notna(d0) else np.nan})
event_df=pd.DataFrame(event_rows)
event_df.to_csv(OUT/'heavy_rain_event_rebound_by_industry.csv', index=False, encoding='utf-8-sig')

# 6h join
six_card=card.groupby(['date','TIME_GB','MCT_SGG_CD','MCT_RY_CD']).agg(sales=('TS_AT','sum'), txn=('USE_CNT','sum')).reset_index()
six_card['dow']=six_card['date'].dt.dayofweek
six_base=six_card.groupby(['MCT_SGG_CD','MCT_RY_CD','TIME_GB','dow']).agg(base_sales=('sales','median'), base_txn=('txn','median')).reset_index()
six=six_card.merge(six_base, on=['MCT_SGG_CD','MCT_RY_CD','TIME_GB','dow'], how='left')
six['sales_dev_pct']=(safe_div(six['sales'], six['base_sales'])-1)*100
six['txn_dev_pct']=(safe_div(six['txn'], six['base_txn'])-1)*100
six_join=six.merge(weather_6h, left_on=['date','TIME_GB','MCT_SGG_CD'], right_on=['date','TIME_GB','region'], how='left')
six_join.to_csv(OUT/'sixhour_region_industry_weather_join.csv', index=False, encoding='utf-8-sig')
six_summary=six_join.groupby(['MCT_SGG_CD','TIME_GB']).agg(
    rows=('sales_dev_pct','count'),
    corr_rain_sales=('rain_6h_mm', lambda x: np.nan),
    mean_sales_dev_rain=('sales_dev_pct', lambda s: s[six_join.loc[s.index,'rain_6h_mm']>0].mean()),
    mean_sales_dev_heavy5=('sales_dev_pct', lambda s: s[six_join.loc[s.index,'rain_6h_mm']>=5].mean()),
).reset_index()
# compute correlations explicitly
corrs=[]
for (region,tb),g in six_join.dropna(subset=['rain_6h_mm','sales_dev_pct']).groupby(['MCT_SGG_CD','TIME_GB']):
    corrs.append({'MCT_SGG_CD':region,'TIME_GB':tb,'corr_rain_sales_dev':g['rain_6h_mm'].corr(g['sales_dev_pct'], method='spearman'), 'heavy5_rows':int((g['rain_6h_mm']>=5).sum())})
six_summary=six_summary.drop(columns=['corr_rain_sales']).merge(pd.DataFrame(corrs), on=['MCT_SGG_CD','TIME_GB'], how='left')
six_summary.to_csv(OUT/'sixhour_timeband_response_summary.csv', index=False, encoding='utf-8-sig')

# Median-based shock, recovery, and topic-priority artifacts
if event_df.empty:
    shock_metrics=pd.DataFrame()
else:
    shock_metrics=event_df.groupby(['region','industry']).agg(
        event_count=('event_date','count'),
        median_event_rain_mm=('rain_mm','median'),
        median_pre3_sales_dev_pct=('pre3_sales_dev_pct','median'),
        median_initial_shock_pp=('d0_sales_dev_pct','median'),
        median_post3_sales_dev_pct=('post3_sales_dev_pct','median'),
        median_rebound_pp=('rebound_gap_pp','median'),
        negative_shock_share=('d0_sales_dev_pct', lambda s: float((s.dropna()<0).mean()) if len(s.dropna()) else np.nan),
        persistent_damage_share=('post3_sales_dev_pct', lambda s: float((s.dropna()<0).mean()) if len(s.dropna()) else np.nan),
        missing_d0_share=('d0_sales_dev_pct', lambda s: float(s.isna().mean())),
    ).reset_index()
    shock_metrics['median_net_damage_pp']=shock_metrics['median_post3_sales_dev_pct']-shock_metrics['median_pre3_sales_dev_pct']
    shock_metrics['median_d0_to_post3_sum_pp']=shock_metrics['median_initial_shock_pp']+shock_metrics['median_post3_sales_dev_pct']

shock_metrics.to_csv(OUT/'shock_recovery_metrics_by_industry.csv', index=False, encoding='utf-8-sig')

six_region=six_summary.groupby('MCT_SGG_CD').agg(
    strongest_negative_6h_corr=('corr_rain_sales_dev','min'),
    negative_6h_bands=('corr_rain_sales_dev', lambda s: int((s<0).sum())),
).reset_index().rename(columns={'MCT_SGG_CD':'region'})

priority=corr.merge(shock_metrics, on=['region','industry'], how='left') if not shock_metrics.empty else corr.copy()
priority=priority.merge(six_region, on='region', how='left')

for col in ['event_count','negative_shock_share','persistent_damage_share','missing_d0_share','median_initial_shock_pp','median_net_damage_pp','median_rebound_pp','median_d0_to_post3_sum_pp']:
    if col not in priority.columns:
        priority[col]=np.nan

priority['event_count_ok']=priority['event_count'].fillna(0)>=8
priority['dry_vs_heavy_agree']=priority['median_heavy20_minus_dry_pp']<0
priority['spearman_agree']=priority['spearman_rain_sales_dev']<0
priority['sixhour_agree']=priority['strongest_negative_6h_corr']<0
priority['initial_shock_agree']=priority['median_initial_shock_pp']<0
priority['persistent_damage_agree']=priority['persistent_damage_share']>=0.5
priority['outlier_flag']=(priority['missing_d0_share'].fillna(1)>0.25) | (priority['event_count'].fillna(0)<5)

priority['priority_score']=(
    (-priority['median_heavy20_minus_dry_pp'].clip(upper=0).fillna(0))*0.35 +
    (-priority['spearman_rain_sales_dev'].clip(upper=0).fillna(0)*100)*0.20 +
    (-priority['median_initial_shock_pp'].clip(upper=0).fillna(0))*0.20 +
    (priority['persistent_damage_share'].fillna(0)*25)*0.10 +
    (-priority['median_net_damage_pp'].clip(upper=0).fillna(0))*0.10 +
    (-priority['strongest_negative_6h_corr'].clip(upper=0).fillna(0)*100)*0.05
)
priority.loc[priority['outlier_flag'], 'priority_score']=priority.loc[priority['outlier_flag'], 'priority_score']*0.75

priority_cols=[
    'region','industry','priority_score','n_days','rain_days','heavy20_days','event_count',
    'spearman_rain_sales_dev','median_heavy20_minus_dry_pp','heavy20_minus_dry_pp','median_initial_shock_pp',
    'median_rebound_pp','median_net_damage_pp','negative_shock_share','persistent_damage_share',
    'strongest_negative_6h_corr','event_count_ok','dry_vs_heavy_agree','spearman_agree',
    'initial_shock_agree','persistent_damage_agree','sixhour_agree','outlier_flag'
]
priority=priority.sort_values('priority_score', ascending=False)
priority[priority_cols].to_csv(OUT/'rainshock_topic_priority_by_industry.csv', index=False, encoding='utf-8-sig')

verification_cols=[
    'region','industry','event_count_ok','dry_vs_heavy_agree','spearman_agree','initial_shock_agree',
    'persistent_damage_agree','sixhour_agree','outlier_flag','negative_shock_share','persistent_damage_share'
]
priority[verification_cols].to_csv(OUT/'rainshock_event_verification_matrix.csv', index=False, encoding='utf-8-sig')

(OUT/'rainshock_topic_priority_top20.json').write_text(
    json.dumps(records(priority[priority_cols].head(20).replace({np.nan:None})), ensure_ascii=False, indent=2),
    encoding='utf-8'
)

# High-level report
report={
    'inputs': {
        'aws400_rows': int(len(aws)),
        'asos101_rows': int(len(asos101)),
        'asos93_rows': int(len(asos93)),
        'card_rows_dataset1': int(len(card)),
        'date_min': str(card['date'].min().date()),
        'date_max': str(card['date'].max().date()),
        'regions': sorted(card['MCT_SGG_CD'].unique().tolist()),
        'industry_count': int(card['MCT_RY_CD'].nunique()),
    },
    'weather': records(weather_daily.groupby('region').agg(days=('date','count'), rain_days=('daily_rain_mm', lambda s:int((s>0).sum())), heavy20_days=('daily_rain_mm', lambda s:int((s>=20).sum())), max_daily_rain=('daily_rain_mm','max'), total_rain=('daily_rain_mm','sum')).reset_index()),
    'rain_bin_summary_topline': records(rain_bin_summary),
    'most_negative_industries_heavy20': records(corr.head(15).replace({np.nan:None})),
    'most_positive_industries_heavy20': records(corr.sort_values('heavy20_minus_dry_pp', ascending=False).head(10).replace({np.nan:None})),
    'sixhour_summary': records(six_summary.replace({np.nan:None})),
    'topic_priority_top10': records(priority[priority_cols].head(10).replace({np.nan:None})),
}
(OUT/'eda_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'status':'ok','out_dir':str(OUT),'files':[p.name for p in sorted(OUT.glob('*'))]}, ensure_ascii=False, indent=2))

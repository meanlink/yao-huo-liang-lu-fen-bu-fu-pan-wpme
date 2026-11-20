import time, os, csv, io, hashlib, json
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from src.models import Job, Report, Delivery, DeliveryVersion, DeliveryGroup, DeliverySign
from src.config.settings import ARTIFACT_DIR
from src.services import briefing


def create(db, data):
    j = db.get(Job, data.job_id)
    if not j or j.status != 'completed' or not j.approved:
        raise HTTPException(409, '请先选择已完成且获批准的分析结果')
    groups = [g.strip() for g in data.groups] if getattr(data, 'groups', None) else []
    groups = [g for g in groups if g]
    if not groups:
        groups = briefing.split_destination(data.destination)  # destination 首段作为默认组
    if len(set(groups)) != len(groups):
        raise HTTPException(422, '收件组不能重复')
    r = Report(name=data.name, job_id=j.id, destination=data.destination,
               interval_seconds=data.interval_seconds, next_run=time.time() + data.delay_seconds, enabled=True)
    db.add(r)
    db.flush()
    briefing.save_report_groups(db, r, groups)
    return r


def archive(db, report, job, channel='scheduled', note='', supersedes=None, groups=None):
    """把一次分析结果落档：生成文件、登记版次、冻结收件组并建待签记录。"""
    out = io.StringIO()
    out.write('﻿')
    table = job.result.get('table', {})
    cols = table.get('columns', [])
    writer = csv.writer(out)

    def safe(v):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return v
        text = str(v)
        return "'" + text if text.startswith(('=', '+', '-', '@', '\t', '\r')) else text

    writer.writerow([safe(c['label']) for c in cols])
    for row in table.get('rows', []):
        writer.writerow([safe(row.get(c.get('key'), '')) for c in cols])
    data = out.getvalue().encode('utf-8')
    delivery = Delivery(report_id=report.id, created_at=time.time(),
                        checksum=hashlib.sha256(data).hexdigest(), filename='',
                        destination=report.destination)
    db.add(delivery)
    db.flush()
    delivery.filename = f'report-{report.id}-delivery-{delivery.id}.csv'
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    with open(os.path.join(ARTIFACT_DIR, delivery.filename), 'wb') as f:
        f.write(data)
    with open(os.path.join(ARTIFACT_DIR, delivery.filename + '.json'), 'w') as f:
        json.dump({'job': job.name, 'params': job.params, 'result': job.result,
                   'checksum': delivery.checksum}, f, ensure_ascii=False, allow_nan=False)

    version = briefing.next_version(db, report.id)
    for attempt in range(4):
        try:
            with db.begin_nested():
                db.add(DeliveryVersion(delivery_id=delivery.id, report_id=report.id, version=version,
                                       job_id=job.id, channel=channel, note=(note or '')[:500],
                                       supersedes_delivery_id=supersedes, created_at=time.time()))
                db.flush()
            break
        except IntegrityError:
            # 并发落档抢到同一版号：重新取号，不产生重复版次
            version = briefing.next_version(db, report.id)
    else:
        raise HTTPException(409, '该计划正在被同时落档，请稍后重试')
    targets = groups if groups is not None else briefing.report_groups(db, report)
    for group in dict.fromkeys(targets):
        db.add(DeliveryGroup(delivery_id=delivery.id, group_name=group))
        db.add(DeliverySign(delivery_id=delivery.id, report_id=report.id, group_name=group,
                            version=version, status='pending', created_at=time.time()))
    report.next_run = time.time() + report.interval_seconds
    return delivery, version


def deliver(db, report):
    j = db.get(Job, report.job_id)
    if not j or not j.approved:
        return
    delivery, _ = archive(db, report, j)
    return delivery


def correction(db, report, job, note=''):
    """向原收件组补发更正版；新版权次独立，旧凭证不计入新版。"""
    if not job or job.status != 'completed' or not job.approved:
        raise HTTPException(409, '补发更正版需要已完成且已批准的分析结果')
    current = briefing.current_version(db, report.id)
    if current is None:
        raise HTTPException(409, '该计划还没有已落档的原件，请等待首次分发')
    superseded = db.get(Delivery, current.delivery_id)
    original = list(db.scalars(select(DeliveryGroup.group_name)
                               .where(DeliveryGroup.delivery_id == current.delivery_id)
                               .order_by(DeliveryGroup.id)))
    if not original:
        original = briefing.report_groups(db, report)
    delivery, version = archive(db, report, job, channel='correction',
                                note=note or f'更正第 {current.version} 版',
                                supersedes=superseded.id if superseded else None, groups=original)
    return delivery, version, original

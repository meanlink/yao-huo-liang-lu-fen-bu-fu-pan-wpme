"""班组收件箱：落档版次、按组建待签记录、组长签收与历版凭证。"""
import time
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from src.models import (Report, Delivery, DeliveryVersion, DeliveryGroup,
                        DeliverySign, GroupMembership, ReportGroup, Audit)


def split_destination(destination):
    first = (destination or '').split(' · ')[0].strip()
    return [first] if first else []


def report_groups(db, report):
    """计划勾选的收件组；旧计划退回到 destination 的首段。"""
    names = list(db.scalars(select(ReportGroup.name).where(ReportGroup.report_id == report.id).order_by(ReportGroup.id)))
    if names:
        return names
    fallback = split_destination(report.destination)
    return fallback


def save_report_groups(db, report, groups):
    existing = {g.name for g in db.scalars(select(ReportGroup).where(ReportGroup.report_id == report.id))}
    for name in groups:
        if name not in existing:
            db.add(ReportGroup(report_id=report.id, name=name))
            existing.add(name)


def current_version(db, report_id):
    return db.scalar(select(DeliveryVersion).where(DeliveryVersion.report_id == report_id)
                     .order_by(DeliveryVersion.version.desc()).limit(1))


def next_version(db, report_id):
    highest = db.scalar(select(func.max(DeliveryVersion.version)).where(DeliveryVersion.report_id == report_id)) or 0
    return highest + 1


def _create_signs_for(db, delivery_id, report_id, version, groups, created):
    existing = set(db.execute(select(DeliverySign.group_name)
                              .where(DeliverySign.delivery_id == delivery_id)).scalars())
    for group in groups:
        if group in existing:
            continue
        try:
            with db.begin_nested():
                db.add(DeliverySign(delivery_id=delivery_id, report_id=report_id,
                                    group_name=group, version=version, status='pending',
                                    created_at=time.time()))
        except IntegrityError:
            # 并发写入或重试：唯一约束保证不重复建单
            continue
        existing.add(group)
        created.append((delivery_id, group))


def ensure_legacy_versions(db):
    """为没有版次记录的旧归档补建 v1，保证收件箱能查到历版。"""
    missing = list(db.scalars(select(Delivery).where(
        ~Delivery.id.in_(select(DeliveryVersion.delivery_id))).order_by(Delivery.created_at, Delivery.id)))
    for delivery in missing:
        report = db.get(Report, delivery.report_id)
        if report is None:
            continue
        try:
            with db.begin_nested():
                db.add(DeliveryVersion(delivery_id=delivery.id, report_id=report.id,
                                       version=next_version(db, report.id), job_id=report.job_id,
                                       channel='scheduled', note='历史归档补登',
                                       created_at=delivery.created_at))
                db.flush()
                for group in report_groups(db, report):
                    db.add(DeliveryGroup(delivery_id=delivery.id, group_name=group))
        except IntegrityError:
            continue


def repair(db):
    """补建缺失的版次与待签记录；可重复调用且不重复建单。"""
    ensure_legacy_versions(db)
    db.flush()
    created = []
    versions = db.execute(select(DeliveryVersion.delivery_id, DeliveryVersion.report_id,
                                 DeliveryVersion.version).order_by(DeliveryVersion.id)).all()
    snapshot = {}
    for delivery_id, group in db.execute(select(DeliveryGroup.delivery_id, DeliveryGroup.group_name)
                                          .order_by(DeliveryGroup.id)).all():
        snapshot.setdefault(delivery_id, []).append(group)
    for delivery_id, report_id, version in versions:
        groups = snapshot.get(delivery_id)
        if not groups:
            report = db.get(Report, report_id)
            groups = report_groups(db, report) if report else []
            for group in groups:  # 快照缺失时补冻收回件组
                db.add(DeliveryGroup(delivery_id=delivery_id, group_name=group))
            db.flush()
        _create_signs_for(db, delivery_id, report_id, version, groups, created)
    if created:
        db.add(Audit(actor='system', action='briefing.signs_recovered',
                     detail={'count': len(created)}, at=time.time()))
    return len(created)


def sign_dict(sign):
    return {'id': sign.id, 'group': sign.group_name, 'version': sign.version, 'status': sign.status,
            'signed_by': sign.signed_by, 'signed_by_name': sign.signed_by_name,
            'signed_at': sign.signed_at, 'read_version': sign.read_version, 'note': sign.note,
            'created_at': sign.created_at}


def version_dict(dv, delivery, signs):
    return {'version': dv.version, 'delivery_id': dv.delivery_id, 'job_id': dv.job_id,
            'channel': dv.channel, 'note': dv.note, 'supersedes_delivery_id': dv.supersedes_delivery_id,
            'archived_at': delivery.created_at, 'checksum': delivery.checksum,
            'filename': delivery.filename, 'destination': delivery.destination,
            'groups': [sign_dict(s) for s in signs]}


def versions_for(db, report_id):
    pairs = db.execute(select(DeliveryVersion, Delivery)
                       .join(Delivery, Delivery.id == DeliveryVersion.delivery_id)
                       .where(DeliveryVersion.report_id == report_id)
                       .order_by(DeliveryVersion.version)).all()
    signs = list(db.scalars(select(DeliverySign).where(DeliverySign.report_id == report_id).order_by(DeliverySign.id)))
    by_delivery = {}
    for sign in signs:
        by_delivery.setdefault(sign.delivery_id, []).append(sign)
    return [version_dict(dv, delivery, by_delivery.get(dv.delivery_id, [])) for dv, delivery in pairs]


def briefing_dict(db, report, mine=None):
    history = versions_for(db, report.id)
    current = history[-1] if history else None
    handover_complete = bool(current and current['groups']) and all(
        g['status'] == 'signed' for g in current['groups'])
    signed_count = sum(g['status'] == 'signed' for g in (current['groups'] if current else []))
    return {'report_id': report.id, 'report_name': report.name, 'destination': report.destination,
            'enabled': report.enabled, 'groups_configured': report_groups(db, report),
            'current_version': current['version'] if current else None,
            'handover_complete': handover_complete,
            'signed_count': signed_count,
            'group_count': len(current['groups']) if current else len(report_groups(db, report)),
            'history': list(reversed(history)), 'current': current,
            'my_groups': mine or []}


def inbox(db, user):
    repair(db)
    db.commit()
    mine = [{'group': m.group_name, 'is_leader': bool(m.is_leader)}
            for m in db.scalars(select(GroupMembership).where(GroupMembership.user_id == user.id)
                                .order_by(GroupMembership.id))]
    reports = list(db.scalars(select(Report).order_by(Report.id.desc())))
    return {'mine': mine, 'briefings': [briefing_dict(db, r, mine) for r in reports]}


def briefing(db, report_id, user):
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(404, '分发计划不存在')
    repair(db)
    db.commit()
    mine = [{'group': m.group_name, 'is_leader': bool(m.is_leader)}
            for m in db.scalars(select(GroupMembership).where(GroupMembership.user_id == user.id)
                                .order_by(GroupMembership.id))]
    return briefing_dict(db, report, mine)


def sign(db, delivery_id, group, note, user):
    """组长签收本组；凭证记录该归档实际版次，绝不计作更新版已读。"""
    group = (group or '').strip()
    if not group:
        raise HTTPException(422, '请选择要签收的收件组')
    repair(db)
    dv = db.scalar(select(DeliveryVersion).where(DeliveryVersion.delivery_id == delivery_id))
    if not dv:
        raise HTTPException(404, '归档版次不存在，请刷新收件箱')
    membership = db.scalar(select(GroupMembership).where(GroupMembership.user_id == user.id,
                                                         GroupMembership.group_name == group))
    if not membership or not membership.is_leader:
        raise HTTPException(403, '只有本组组长可以签收，其他成员请转交组长')
    if not db.scalar(select(DeliveryGroup).where(DeliveryGroup.delivery_id == delivery_id,
                                                  DeliveryGroup.group_name == group)):
        raise HTTPException(422, '该组不在这一版的收件范围内')
    row = db.scalar(select(DeliverySign).where(DeliverySign.delivery_id == delivery_id,
                                               DeliverySign.group_name == group).with_for_update())
    if row is None:
        # 极端情况：版次与组的快照存在而待签记录缺失，当场补建
        try:
            with db.begin_nested():
                row = DeliverySign(delivery_id=delivery_id, report_id=dv.report_id, group_name=group,
                                   version=dv.version, status='pending', created_at=time.time())
                db.add(row)
                db.flush()
        except IntegrityError:
            row = db.scalar(select(DeliverySign)
                            .where(DeliverySign.delivery_id == delivery_id,
                                   DeliverySign.group_name == group).with_for_update())
            if row is None:
                raise HTTPException(409, '签收记录正在生成，请刷新后重试')
    if row.status == 'signed':
        if row.signed_by == user.email:
            return row, dv
        raise HTTPException(409, f'{group} 已由 {row.signed_by_name or row.signed_by} 签收')
    row.status = 'signed'
    row.signed_by = user.email
    row.signed_by_name = user.name
    row.signed_at = time.time()
    row.read_version = dv.version  # 实际读到的版次，而非签收时的最新版
    row.note = (note or '').strip()[:500]
    # 只有签的就是当前最新版，才算这一组读到了新版；签旧版只算旧版已读。
    latest = current_version(db, dv.report_id)
    db.add(Audit(actor=user.email, action='briefing.sign',
                 detail={'report_id': dv.report_id, 'delivery_id': delivery_id,
                         'version': dv.version, 'latest_version': latest.version if latest else None,
                         'group': group}, at=time.time()))
    db.flush()
    return row, dv


def group_catalog(db):
    report_names = set(db.scalars(select(ReportGroup.name)))
    memberships = list(db.scalars(select(GroupMembership).order_by(GroupMembership.group_name, GroupMembership.id)))
    names = sorted({m.group_name for m in memberships} | report_names)
    leaders = {}
    for m in memberships:
        if m.is_leader:
            leaders.setdefault(m.group_name, []).append(m.user_id)
    from src.models import User
    result = []
    for name in names:
        people = [db.get(User, uid) for uid in leaders.get(name, [])]
        result.append({'name': name, 'leaders': [{'email': u.email, 'name': u.name} for u in people if u]})
    return result

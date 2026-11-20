from sqlalchemy import String, Double, ForeignKey, Boolean, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base


class GroupMembership(Base):
    """用户的收件组归属；只有组长可以代表本组签收。"""
    __tablename__ = 'group_memberships'
    __table_args__ = (UniqueConstraint('user_id', 'group_name', name='uq_group_membership'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    group_name: Mapped[str] = mapped_column(String(80))
    is_leader: Mapped[bool] = mapped_column(Boolean, default=False)


class ReportGroup(Base):
    """分发计划勾选的收件组。"""
    __tablename__ = 'report_groups'
    __table_args__ = (UniqueConstraint('report_id', 'name', name='uq_report_group'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey('reports.id'))
    name: Mapped[str] = mapped_column(String(80))


class DeliveryVersion(Base):
    """每次落档的简报版次；当前版即该计划下版次最大的归档。"""
    __tablename__ = 'delivery_versions'
    __table_args__ = (
        UniqueConstraint('delivery_id', name='uq_delivery_version_delivery'),
        UniqueConstraint('report_id', 'version', name='uq_delivery_version_report'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey('deliveries.id'))
    report_id: Mapped[int] = mapped_column(ForeignKey('reports.id'))
    version: Mapped[int] = mapped_column(Integer)
    job_id: Mapped[int] = mapped_column(ForeignKey('jobs.id'))
    channel: Mapped[str] = mapped_column(String(20), default='scheduled')
    note: Mapped[str] = mapped_column(String(500), default='')
    supersedes_delivery_id: Mapped[int | None] = mapped_column(ForeignKey('deliveries.id'), nullable=True)
    created_at: Mapped[float] = mapped_column(Double)


class DeliveryGroup(Base):
    """落档时冻结的收件组快照，之后计划改动不影响历史版。"""
    __tablename__ = 'delivery_groups'
    __table_args__ = (UniqueConstraint('delivery_id', 'group_name', name='uq_delivery_group'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey('deliveries.id'))
    group_name: Mapped[str] = mapped_column(String(80))


class DeliverySign(Base):
    """按收件组生成的待签/签收凭证，记录实际读到的版次。"""
    __tablename__ = 'delivery_signs'
    __table_args__ = (UniqueConstraint('delivery_id', 'group_name', name='uq_delivery_sign'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey('deliveries.id'))
    report_id: Mapped[int] = mapped_column(ForeignKey('reports.id'))
    group_name: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    signed_by: Mapped[str] = mapped_column(String(150), default='')
    signed_by_name: Mapped[str] = mapped_column(String(80), default='')
    signed_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    read_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str] = mapped_column(String(500), default='')
    created_at: Mapped[float] = mapped_column(Double)

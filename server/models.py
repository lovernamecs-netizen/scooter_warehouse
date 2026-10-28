from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, JSON, UniqueConstraint, CheckConstraint, Index, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

def uid(): return str(uuid4())
def now(): return datetime.now(timezone.utc)
class Base(DeclarativeBase): pass
class Guard(Base):
    __tablename__='guard'
    id: Mapped[int]=mapped_column(primary_key=True)
    revision: Mapped[int]=mapped_column(default=0)
class User(Base):
    __tablename__='users'
    id: Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    username: Mapped[str]=mapped_column(String,unique=True)
    password: Mapped[str]
    role: Mapped[str]=mapped_column(default='worker')
    active: Mapped[bool]=mapped_column(default=True)
class Session(Base):
    __tablename__='sessions'
    id: Mapped[str]=mapped_column(String,primary_key=True)
    user_id: Mapped[str]=mapped_column(ForeignKey('users.id'))
    expires: Mapped[datetime]=mapped_column(DateTime(timezone=True))
class SecurityOwner(Base):
    __tablename__='security_owner'
    id: Mapped[int]=mapped_column(primary_key=True)
    user_id: Mapped[str]=mapped_column(ForeignKey('users.id'),unique=True)
class CustomerAccess(Base):
    __tablename__='customer_access'
    user_id: Mapped[str]=mapped_column(ForeignKey('users.id'),primary_key=True)
    allowed: Mapped[bool]=mapped_column(default=False)
    granted_by: Mapped[str]=mapped_column(ForeignKey('users.id'))
class Customer(Base):
    __tablename__='customers'
    id: Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    kind: Mapped[str]
    encrypted_name: Mapped[str]
    created_by: Mapped[str]=mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    request_id: Mapped[str]=mapped_column(String,unique=True)
    request_digest: Mapped[str]
class CustomerSearch(Base):
    __tablename__='customer_search'
    token: Mapped[str]=mapped_column(String,primary_key=True)
    customer_id: Mapped[str]=mapped_column(ForeignKey('customers.id'),primary_key=True,index=True)
class OrderCustomer(Base):
    __tablename__='order_customers'
    order_id: Mapped[str]=mapped_column(ForeignKey('orders.id'),primary_key=True)
    customer_id: Mapped[str]=mapped_column(ForeignKey('customers.id'),index=True)
    encrypted_name: Mapped[str]
    kind: Mapped[str]
class OutboundCustomer(Base):
    __tablename__='outbound_customers'
    __table_args__=(Index('customer_dispatch_page','customer_id','at','outbound_id'),)
    outbound_id: Mapped[str]=mapped_column(ForeignKey('outbound.id'),primary_key=True)
    order_id: Mapped[str]=mapped_column(ForeignKey('orders.id'),index=True)
    customer_id: Mapped[str]=mapped_column(ForeignKey('customers.id'),index=True)
    encrypted_name: Mapped[str]
    kind: Mapped[str]
    at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class CustomerAudit(Base):
    __tablename__='customer_audit'
    id: Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,index=True)
    actor_id: Mapped[str]=mapped_column(ForeignKey('users.id'))
    event: Mapped[str]
    target_id: Mapped[str]=mapped_column(default='')
class VehicleCustomerEvent(Base):
    """Append-only relationship events; original dispatch is never rewritten by succession."""
    __tablename__='vehicle_customer_events'
    __table_args__=(CheckConstraint("kind IN ('DELIVERY','TRANSFER')"),)
    id: Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    vehicle_id: Mapped[str]=mapped_column(ForeignKey('vehicles.id'),index=True)
    customer_id: Mapped[str]=mapped_column(ForeignKey('customers.id'),index=True)
    previous_customer_id: Mapped[str|None]=mapped_column(ForeignKey('customers.id'),nullable=True)
    previous_event_id: Mapped[str|None]=mapped_column(ForeignKey('vehicle_customer_events.id'),nullable=True,unique=True)
    outbound_id: Mapped[str]=mapped_column(ForeignKey('outbound.id'),index=True)
    kind: Mapped[str]=mapped_column(default='DELIVERY')
    effective_day: Mapped[str]
    encrypted_reason: Mapped[str]=mapped_column(default='')
    actor_id: Mapped[str]=mapped_column(ForeignKey('users.id'))
    at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Master(Base):
    __tablename__='masters'
    id: Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    kind: Mapped[str]
    name: Mapped[str]
    detail: Mapped[dict]=mapped_column(JSON,default=dict)
    active: Mapped[bool]=mapped_column(default=True)
    version: Mapped[int]=mapped_column(default=1)
    __table_args__=(UniqueConstraint('kind','name'),)
class Vehicle(Base):
    __tablename__='vehicles'
    id: Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    vin: Mapped[str]=mapped_column(String,unique=True)
    model_id: Mapped[str]=mapped_column(ForeignKey('masters.id'))
    color_id: Mapped[str]=mapped_column(ForeignKey('masters.id'))
    year: Mapped[int]
    manufactured_month: Mapped[str | None] = mapped_column(String(7),nullable=True)
    kind: Mapped[str]=mapped_column(default='NEW')
    plate: Mapped[str]=mapped_column(default='')
    smart_key: Mapped[str]=mapped_column(default='')
    serial_number: Mapped[str]=mapped_column(default='')
    ubis_number: Mapped[str]=mapped_column(default='')
    notes: Mapped[str]=mapped_column(default='')
    ubis: Mapped[str]=mapped_column(default='NOT_INSTALLED')
    version: Mapped[int]=mapped_column(default=1)
    archived: Mapped[bool]=mapped_column(default=False)
class Stay(Base):
    __tablename__='stays'
    id: Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    vehicle_id: Mapped[str]=mapped_column(ForeignKey('vehicles.id'))
    received_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    closed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    first_placed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    reason: Mapped[str]=mapped_column(default='RECEIPT')
Index('one_open_stay',Stay.vehicle_id,unique=True,sqlite_where=text('closed_at IS NULL'),postgresql_where=text('closed_at IS NULL'))
class Zone(Base):
    __tablename__='zones'
    __table_args__=(CheckConstraint('rows > 0 AND cols > 0'),)
    id: Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    name: Mapped[str]=mapped_column(String,unique=True)
    kind: Mapped[str]=mapped_column(default='STORAGE')
    rows: Mapped[int]=mapped_column(default=2)
    cols: Mapped[int]=mapped_column(default=6)
    x: Mapped[int]=mapped_column(default=20)
    y: Mapped[int]=mapped_column(default=20)
    model_ids: Mapped[list]=mapped_column(JSON,default=list)
    active: Mapped[bool]=mapped_column(default=True)
    version: Mapped[int]=mapped_column(default=1)
class Slot(Base):
    __tablename__='slots'
    id: Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    zone_id: Mapped[str]=mapped_column(ForeignKey('zones.id'))
    row: Mapped[int]
    col: Mapped[int]
    label: Mapped[str]
    enabled: Mapped[bool]=mapped_column(default=True)
    __table_args__=(UniqueConstraint('zone_id','row','col'),UniqueConstraint('zone_id','label'))
class Placement(Base):
    __tablename__='placements'
    stay_id: Mapped[str]=mapped_column(ForeignKey('stays.id'),primary_key=True)
    slot_id: Mapped[str]=mapped_column(ForeignKey('slots.id'),unique=True)
class LayoutRevision(Base):
    __tablename__='layout_revisions'
    id: Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    actor: Mapped[str]
    snapshot: Mapped[dict]=mapped_column(JSON)
class Order(Base):
    __tablename__='orders'
    id: Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    number: Mapped[str]=mapped_column(String,unique=True)
    notes: Mapped[str]=mapped_column(default='')
class Assignment(Base):
    __tablename__='assignments'
    id: Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    order_id: Mapped[str]=mapped_column(ForeignKey('orders.id'))
    stay_id: Mapped[str]=mapped_column(ForeignKey('stays.id'))
    scheduled: Mapped[str]
    status: Mapped[str]=mapped_column(default='ACTIVE')
    work: Mapped[str]=mapped_column(default='PENDING')
    ready: Mapped[bool]=mapped_column(default=False)
Index('one_active_assignment',Assignment.stay_id,unique=True,sqlite_where=text("status='ACTIVE'"),postgresql_where=text("status='ACTIVE'"))
class OptionLine(Base):
    __tablename__='order_options'
    __table_args__=(CheckConstraint('qty >= 0 AND done >= 0 AND done <= qty'),)
    id: Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    assignment_id: Mapped[str]=mapped_column(ForeignKey('assignments.id'))
    master_id: Mapped[str]=mapped_column(ForeignKey('masters.id'))
    item: Mapped[dict]=mapped_column(JSON)
    qty: Mapped[int]
    done: Mapped[int]=mapped_column(default=0)
    required: Mapped[bool]=mapped_column(default=True)
class DeliveryLine(Base):
    __tablename__='delivery_items'
    __table_args__=(CheckConstraint('qty >= 0 AND done >= 0 AND done <= qty AND handed >= 0 AND handed <= done'),)
    id: Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    assignment_id: Mapped[str]=mapped_column(ForeignKey('assignments.id'))
    master_id: Mapped[str|None]=mapped_column(ForeignKey('masters.id'),nullable=True)
    item: Mapped[dict]=mapped_column(JSON)
    qty: Mapped[int]
    done: Mapped[int]=mapped_column(default=0)
    handed: Mapped[int]=mapped_column(default=0)
    required: Mapped[bool]=mapped_column(default=True)
class Equipment(Base):
    __tablename__='equipment'
    __table_args__=(CheckConstraint('qty >= 0'),)
    id: Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    vehicle_id: Mapped[str]=mapped_column(ForeignKey('vehicles.id'))
    line_id: Mapped[str|None]=mapped_column(ForeignKey('order_options.id'),unique=True,nullable=True)
    item: Mapped[dict]=mapped_column(JSON)
    qty: Mapped[int]
    origin: Mapped[str]=mapped_column(default='EXISTING')
class Outbound(Base):
    __tablename__='outbound'
    id: Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    stay_id: Mapped[str]=mapped_column(ForeignKey('stays.id'),unique=True)
    vehicle_id: Mapped[str]=mapped_column(ForeignKey('vehicles.id'))
    at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    day: Mapped[str]=mapped_column(index=True)
    snapshot: Mapped[dict]=mapped_column(JSON)
class Adjustment(Base):
    __tablename__='adjustments'
    id: Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    outbound_id: Mapped[str]=mapped_column(ForeignKey('outbound.id'))
    at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    kind: Mapped[str]
    reason: Mapped[str]
    actor: Mapped[str]
    detail: Mapped[dict]=mapped_column(JSON,default=dict)
class History(Base):
    __tablename__='history'
    id: Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    vehicle_id: Mapped[str|None]=mapped_column(ForeignKey('vehicles.id'),nullable=True,index=True)
    at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    event: Mapped[str]
    actor: Mapped[str]
    data: Mapped[dict]=mapped_column(JSON,default=dict)
class Closing(Base):
    __tablename__='closings'
    day: Mapped[str]=mapped_column(String,primary_key=True)
    at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    actor: Mapped[str]
    snapshot: Mapped[dict]=mapped_column(JSON)
class Command(Base):
    __tablename__='commands'
    id: Mapped[str]=mapped_column(String,primary_key=True)
    digest: Mapped[str]
    user_id: Mapped[str]
    result: Mapped[dict]=mapped_column(JSON)
class Setting(Base):
    __tablename__='settings'
    key: Mapped[str]=mapped_column(String,primary_key=True)
    value: Mapped[dict]=mapped_column(JSON)
class ImportJob(Base):
    __tablename__='imports'
    id: Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    digest: Mapped[str]=mapped_column(String,unique=True)
    actor: Mapped[str]
    rows: Mapped[list]=mapped_column(JSON)
    applied: Mapped[bool]=mapped_column(default=False)
    at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)


# Vehicle-only inventory history; intentionally independent of the parts ledger.
class VehicleInventorySnapshot(Base):
    __tablename__='vehicle_inventory_snapshots'
    id: Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    day: Mapped[str]=mapped_column(String,index=True)
    version: Mapped[int]=mapped_column(Integer)
    source: Mapped[str]
    signature: Mapped[str]
    data: Mapped[dict]=mapped_column(JSON)
    previous_id: Mapped[str|None]=mapped_column(String,nullable=True)
    actor: Mapped[str]
    at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(UniqueConstraint('day','version'),)
class VehicleInventoryEvent(Base):
    __tablename__='vehicle_inventory_events'
    id: Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    day: Mapped[str]=mapped_column(String,index=True)
    kind: Mapped[str]
    basis_id: Mapped[str|None]=mapped_column(String,nullable=True)
    signature: Mapped[str]
    data: Mapped[dict]=mapped_column(JSON)
    actor: Mapped[str]
    at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class VehicleValuation(Base):
    __tablename__='vehicle_valuations'
    id: Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    scope: Mapped[str]
    target_id: Mapped[str]=mapped_column(String,index=True)
    vehicle_kind: Mapped[str]
    effective_day: Mapped[str]=mapped_column(String,index=True)
    amount: Mapped[int|None]=mapped_column(Integer,nullable=True)
    reason: Mapped[str]
    actor: Mapped[str]
    at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class VehicleInventoryFact(Base):
    __tablename__='vehicle_inventory_facts'
    id: Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    vehicle_id: Mapped[str]=mapped_column(String,index=True)
    effective_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),index=True)
    data: Mapped[dict]=mapped_column(JSON)
    actor: Mapped[str]
    at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class VehicleInventoryRequest(Base):
    __tablename__='vehicle_inventory_requests'
    id: Mapped[str]=mapped_column(String,primary_key=True)
    digest: Mapped[str]
    result: Mapped[dict]=mapped_column(JSON)

class PurchaseRecord(Base):
    __tablename__='purchase_records'
    id: Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    record_id: Mapped[str]=mapped_column(String,index=True)
    revision: Mapped[int]
    source_key: Mapped[str]=mapped_column(String,index=True)
    data: Mapped[dict]=mapped_column(JSON)
    vehicle_id: Mapped[str|None]=mapped_column(String,nullable=True)
    stay_id: Mapped[str|None]=mapped_column(String,nullable=True)
    actor: Mapped[str]
    at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(UniqueConstraint('record_id','revision'),)

class PurchaseReviewEvent(Base):
    __tablename__='purchase_review_events'
    id: Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    kind: Mapped[str]
    data: Mapped[dict]=mapped_column(JSON)
    actor: Mapped[str]
    at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

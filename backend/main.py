from fastapi import FastAPI, HTTPException, Depends
from contextlib import asynccontextmanager
from pydantic import BaseModel, ConfigDict
from sqlalchemy import create_engine, Column, Integer, String, Numeric, DateTime, ForeignKey, or_, func, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship, backref
from sqlalchemy import event
from datetime import datetime
from typing import Optional, List
import os

# --- 1. 数据库基础配置 ---
if not os.path.exists("./data"):
    try:
        os.makedirs("./data")
        print("✅ 已创建 ./data 目录")
    except Exception as e:
        print(f"⚠️ 创建目录失败: {e}")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/ledger.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- 2. 数据库模型定义 ---

class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    type = Column(String)
    parent_id = Column(Integer, ForeignKey('categories.id', ondelete="CASCADE"), nullable=True)
    children = relationship("Category", backref=backref('parent', remote_side=[id]), cascade="all, delete")

class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    type = Column(String)
    initial_balance = Column(Numeric(10, 2), default=0.00)
    billing_day = Column(Integer, nullable=True)
    due_day = Column(Integer, nullable=True)
    sent_transactions = relationship("Transaction", foreign_keys="Transaction.account_id", back_populates="account", cascade="all, delete")
    received_transactions = relationship("Transaction", foreign_keys="Transaction.target_account_id", back_populates="target_account", cascade="all, delete")

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime)
    type = Column(String)
    amount = Column(Numeric(10, 2))
    category = Column(String)
    tag = Column(String, nullable=True)
    note = Column(String, nullable=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"))
    target_account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True)
    link_id = Column(Integer, ForeignKey("transactions.id", ondelete="CASCADE"), nullable=True)
    
    # [新增] 排序字段，默认为 0
    sort_order = Column(Integer, default=0)

    account = relationship("Account", foreign_keys=[account_id], back_populates="sent_transactions", lazy='joined')
    target_account = relationship("Account", foreign_keys=[target_account_id], back_populates="received_transactions", lazy='joined')
    
    @property
    def account_name(self): return self.account.name if self.account else "未知账户"
    
    @property
    def target_account_name(self): return self.target_account.name if self.target_account else None

# --- 3. Pydantic Models ---

class CategoryCreate(BaseModel):
    name: str; type: str; parent_id: Optional[int] = None
class CategoryUpdate(BaseModel):
    name: str; type: str; parent_id: Optional[int] = None
class CategoryOut(CategoryCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)

class AccountCreate(BaseModel):
    name: str; type: str; initial_balance: float = 0.0; billing_day: Optional[int] = None; due_day: Optional[int] = None
class AccountUpdate(AccountCreate): pass
class AccountOut(AccountCreate):
    id: int; balance: float
    model_config = ConfigDict(from_attributes=True)

class TransactionCreate(BaseModel):
    date: datetime; type: str; amount: float; category: str = "转账"; 
    tag: Optional[str] = None; note: Optional[str] = None; 
    account_id: int; target_account_id: Optional[int] = None; fund_account_id: Optional[int] = None

class TransactionUpdate(BaseModel):
    date: datetime; type: str; amount: float; category: str; 
    tag: Optional[str] = None; note: Optional[str] = None; 
    account_id: int; target_account_id: Optional[int] = None

class TransactionOut(TransactionCreate):
    id: int; account_name: str; target_account_name: Optional[str] = None; link_id: Optional[int] = None; 
    sort_order: int # 返回排序字段
    model_config = ConfigDict(from_attributes=True)

# [新增] 批量排序请求模型
class SortItem(BaseModel):
    id: int
    sort_order: int

# --- 4. 初始化与迁移 ---
def check_and_migrate_db():
    """检查数据库结构并自动迁移"""
    print("🔄 检查数据库结构...")
    Base.metadata.create_all(bind=engine)
    
    # 简单的迁移逻辑：检查 transactions 表是否有 sort_order 字段
    with engine.connect() as conn:
        try:
            # 尝试查询 sort_order，如果报错说明字段不存在
            conn.execute(text("SELECT sort_order FROM transactions LIMIT 1"))
        except Exception:
            print("⚠️ 检测到缺少 sort_order 字段，正在自动添加...")
            try:
                conn.execute(text("ALTER TABLE transactions ADD COLUMN sort_order INTEGER DEFAULT 0"))
                conn.commit()
                print("✅ 字段 sort_order 添加成功")
            except Exception as e:
                print(f"❌ 自动迁移失败: {e}")

# --- 5. FastAPI 配置 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    check_and_migrate_db()
    init_default_data()
    yield

app = FastAPI(lifespan=lifespan)

def get_db():
    db = SessionLocal(); try: yield db; finally: db.close()

def init_default_data():
    db = SessionLocal()
    if db.query(Category).count() == 0:
        print("📦 写入默认分类数据...")
        data = [
            {"name": "餐饮", "type": "EXPENSE", "children": ["早餐", "午餐", "晚餐", "饮料", "零食"]},
            {"name": "交通", "type": "EXPENSE", "children": ["地铁", "公交", "打车", "加油", "停车"]},
            {"name": "购物", "type": "EXPENSE", "children": ["服饰", "日用", "数码", "美妆"]},
            {"name": "居住", "type": "EXPENSE", "children": ["房租", "水电", "宽带", "物业"]},
            {"name": "工资", "type": "INCOME", "children": []},
            {"name": "理财", "type": "INCOME", "children": ["利息", "基金", "股票"]}
        ]
        for item in data:
            parent = Category(name=item["name"], type=item["type"])
            db.add(parent); db.commit(); db.refresh(parent)
            for child in item["children"]: db.add(Category(name=child, type=item["type"], parent_id=parent.id))
        db.commit()
    db.close()

# --- 6. API 接口 ---

# Categories & Accounts (保持不变，省略具体实现以节省篇幅，功能与之前一致)
@app.get("/api/categories", response_model=List[CategoryOut])
def read_categories(db: Session = Depends(get_db)): return db.query(Category).all()
@app.post("/api/categories", response_model=CategoryOut)
def create_category(c: CategoryCreate, db: Session = Depends(get_db)): o=Category(name=c.name,type=c.type,parent_id=c.parent_id); db.add(o); db.commit(); db.refresh(o); return o
@app.put("/api/categories/{id}", response_model=CategoryOut)
def update_category(id: int, c: CategoryUpdate, db: Session = Depends(get_db)): o=db.query(Category).filter(Category.id==id).first(); o.name=c.name; o.type=c.type; o.parent_id=c.parent_id; db.commit(); db.refresh(o); return o
@app.delete("/api/categories/{id}")
def delete_category(id: int, db: Session = Depends(get_db)): db.query(Category).filter(Category.id==id).delete(); db.commit(); return {"ok":True}

@app.get("/api/accounts", response_model=List[AccountOut])
def read_accounts(db: Session = Depends(get_db)):
    # 聚合计算余额 (保持之前的优化)
    accounts = db.query(Account).all()
    from_stats = db.query(Transaction.account_id, Transaction.type, func.sum(Transaction.amount)).group_by(Transaction.account_id, Transaction.type).all()
    to_stats = db.query(Transaction.target_account_id, func.sum(Transaction.amount)).filter(Transaction.type=='TRANSFER').group_by(Transaction.target_account_id).all()
    b_map = {a.id: a.initial_balance for a in accounts}
    for aid, t, amt in from_stats:
        if aid: b_map[aid] += amt if t=='INCOME' else -amt
    for aid, amt in to_stats:
        if aid: b_map[aid] += amt
    for a in accounts: a.balance = b_map.get(a.id, 0)
    return accounts
@app.post("/api/accounts", response_model=AccountOut)
def create_account(a: AccountCreate, db: Session = Depends(get_db)): o=Account(**a.model_dump()); db.add(o); db.commit(); db.refresh(o); o.balance=o.initial_balance; return o
@app.put("/api/accounts/{id}", response_model=AccountOut)
def update_account(id: int, a: AccountUpdate, db: Session = Depends(get_db)): o=db.query(Account).filter(Account.id==id).first(); [setattr(o,k,v) for k,v in a.model_dump().items()]; db.commit(); db.refresh(o); o.balance=o.initial_balance; return o
@app.delete("/api/accounts/{id}")
def delete_account(id: int, db: Session = Depends(get_db)): db.query(Account).filter(Account.id==id).delete(); db.commit(); return {"ok":True}

# === Transactions (修改排序逻辑) ===
@app.get("/api/transactions", response_model=List[TransactionOut])
def read_transactions(account_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(Transaction)
    if account_id: q = q.filter(or_(Transaction.account_id == account_id, Transaction.target_account_id == account_id))
    # [修改] 排序逻辑：日期降序 -> sort_order 升序 -> ID 降序
    return q.order_by(Transaction.date.desc(), Transaction.sort_order.asc(), Transaction.id.desc()).all()

@app.post("/api/transactions", response_model=TransactionOut)
def create_transaction(item: TransactionCreate, db: Session = Depends(get_db)):
    if item.type == "TRANSFER":
        if not item.target_account_id or item.account_id == item.target_account_id: raise HTTPException(400, "转账账户错误")
    if item.type == "EXPENSE" and item.fund_account_id and item.account_id == item.fund_account_id: raise HTTPException(400, "资金账户错误")

    # 新增记录 sort_order 默认为 0，或者你可以查询当前最大值+1（这里简化处理，手动排序后再更新）
    db_item = Transaction(**item.model_dump(exclude={'fund_account_id'}))
    db.add(db_item); db.flush()

    if item.type == "EXPENSE" and item.fund_account_id:
        db.add(Transaction(
            date=item.date, type="TRANSFER", amount=item.amount, category="转账",
            account_id=item.fund_account_id, target_account_id=item.account_id,
            note=f"自动转账 ({item.category})", link_id=db_item.id
        ))
    db.commit(); db.refresh(db_item); return db_item

@app.put("/api/transactions/{id}", response_model=TransactionOut)
def update_transaction(id: int, item: TransactionUpdate, db: Session = Depends(get_db)):
    o = db.query(Transaction).filter(Transaction.id==id).first()
    if not o: raise HTTPException(404)
    [setattr(o, k, v) for k, v in item.model_dump().items()]
    db.commit(); db.refresh(o); return o

@app.delete("/api/transactions/{id}")
def delete_transaction(id: int, db: Session = Depends(get_db)):
    db.query(Transaction).filter(or_(Transaction.id==id, Transaction.link_id==id)).delete()
    db.commit(); return {"ok": True}

# [新增] 重新排序接口
@app.post("/api/transactions/reorder")
def reorder_transactions(items: List[SortItem], db: Session = Depends(get_db)):
    # 批量更新
    for item in items:
        db.query(Transaction).filter(Transaction.id == item.id).update({"sort_order": item.sort_order})
    db.commit()
    return {"ok": True}
<script setup>
import { ref, onMounted, computed } from 'vue'

const activeView = ref('transactions'); const settingsTab = ref('accounts')
const accounts = ref([]); const categories = ref([]); const transactions = ref([])
const selectedAccount = ref(null)

const filterMode = ref('MONTH') 
const cursorDate = ref(new Date())

const showRecordModal = ref(false); const showAccountModal = ref(false); const showCategoryModal = ref(false)
const form = ref({ type: 'EXPENSE', date: new Date().toISOString().split('T')[0], amount: '', category: '', tag: '', note: '', account_id: '', target_account_id: '', fund_account_id: '' })
const commonTags = ['支付宝', '微信', '云闪付', '美团', '京东', '报销', '出差']
const isTransactionEdit = ref(false); const editTransactionId = ref(null)
const isAccountEdit = ref(false); const editAccountId = ref(null)
const accountForm = ref({ name: '', type: '现金', initial_balance: '', billing_day: '', due_day: '' })
const isCatEdit = ref(false); const editCatId = ref(null)
const categoryForm = ref({ name: '', type: 'EXPENSE', parent_id: '' })

// [新增] 报表视图的选中状态
const selectedReport = ref('overview')

// --- 拖拽状态 ---
const draggingId = ref(null)
const draggingDate = ref(null)

const fetchData = async () => {
  try {
    const [acc, cat, trans] = await Promise.all([
      fetch('/api/accounts').then(r => r.json()),
      fetch('/api/categories').then(r => r.json()),
      fetch('/api/transactions').then(r => r.json())
    ])
    accounts.value = acc; categories.value = cat; transactions.value = trans
    if (acc.length > 0 && !form.value.account_id) form.value.account_id = acc[0].id
    if (!isTransactionEdit.value) setDefaultCategory()
  } catch (e) { console.error(e) }
}

const openCreateTransaction = () => {
  isTransactionEdit.value = false; editTransactionId.value = null
  const now = new Date(); const today = new Date(now.getTime() - (now.getTimezoneOffset() * 60000)).toISOString().split('T')[0];
  form.value = { type: 'EXPENSE', date: today, amount: '', category: '', tag: '', note: '', account_id: accounts.value[0]?.id || '', target_account_id: '', fund_account_id: '' }
  setDefaultCategory(); showRecordModal.value = true
}
const openEditTransaction = (t) => {
  isTransactionEdit.value = true; editTransactionId.value = t.id
  form.value = { type: t.type, date: t.date.split('T')[0], amount: t.amount, category: t.category, tag: t.tag||'', note: t.note||'', account_id: t.account_id, target_account_id: t.target_account_id||'', fund_account_id: '' }
  showRecordModal.value = true
}
const submitTransaction = async (keepOpen = false) => {
  if (!form.value.amount || !form.value.account_id) return alert('请补全信息')
  if (form.value.type !== 'TRANSFER' && !form.value.category) return alert('请选择分类')
  const payload = {
    date: new Date(form.value.date).toISOString(), type: form.value.type, amount: Number(form.value.amount),
    category: form.value.type === 'TRANSFER' ? '转账' : form.value.category,
    tag: form.value.tag || null, note: form.value.note || null,
    account_id: Number(form.value.account_id), target_account_id: form.value.target_account_id ? Number(form.value.target_account_id) : null,
  }
  let url = '/api/transactions'; let method = 'POST'
  if (isTransactionEdit.value) { url = `/api/transactions/${editTransactionId.value}`; method = 'PUT' } 
  else { payload.fund_account_id = (form.value.type === 'EXPENSE' && form.value.fund_account_id) ? Number(form.value.fund_account_id) : null }
  
  const res = await fetch(url, { method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) })
  if (res.ok) { 
    await fetchData(); 
    if(keepOpen) { form.value.amount=''; form.value.note=''; form.value.tag=''; } else showRecordModal.value = false 
  } else alert('保存失败')
}

// --- 拖拽排序逻辑 ---
const onDragStart = (evt, t) => {
  draggingId.value = t.id
  draggingDate.value = t.date.split('T')[0]
  evt.dataTransfer.effectAllowed = 'move'
  // 给被拖动元素加个样式类（可选）
  evt.target.classList.add('dragging-row')
}

const onDragOver = (evt, t) => {
  const targetDate = t.date.split('T')[0]
  // 核心：如果日期不同，禁止放置
  if (targetDate !== draggingDate.value) {
    evt.dataTransfer.dropEffect = 'none'
    return
  }
  evt.preventDefault() // 允许 drop
  evt.dataTransfer.dropEffect = 'move'
}

const onDrop = async (evt, targetT) => {
  evt.target.classList.remove('dragging-row')
  const targetDate = targetT.date.split('T')[0]
  
  if (targetDate !== draggingDate.value || targetT.id === draggingId.value) return

  // 1. 在本地 transactions 数组中找到这两个元素的索引
  // 注意：因为 filteredTransactions 是计算属性，我们必须操作源数据 transactions
  // 也可以简单点，只对当前视图显示的列表进行重排，然后同步回源数据
  
  // 更好的策略：提取出同日期的所有交易
  const sameDayTrans = transactions.value.filter(t => t.date.split('T')[0] === draggingDate.value)
  
  // 按照当前的 sort_order (如果还没排过序可能是乱的，或者按ID) 排序
  // 这里我们直接依赖数组当前的顺序，因为 fetch 时已经排好了
  
  const oldIndex = sameDayTrans.findIndex(t => t.id === draggingId.value)
  const newIndex = sameDayTrans.findIndex(t => t.id === targetT.id)
  
  if (oldIndex === -1 || newIndex === -1) return

  // 2. 移动元素
  const [movedItem] = sameDayTrans.splice(oldIndex, 1)
  sameDayTrans.splice(newIndex, 0, movedItem)

  // 3. 重新计算该日期下所有元素的 sort_order
  const updates = sameDayTrans.map((t, index) => ({
    id: t.id,
    sort_order: index // 0, 1, 2...
  }))

  // 4. 乐观更新：直接更新本地 transactions 列表的 sort_order，让界面立刻反应
  updates.forEach(u => {
    const t = transactions.value.find(tx => tx.id === u.id)
    if (t) t.sort_order = u.sort_order
  })
  // 触发 reactivity: Vue 3 需要一点 hack 或者重新赋值来确保 computed 重新计算顺序
  // 由于 filteredTransactions 依赖 sort_order，我们需要确保数组变更被检测到
  transactions.value = [...transactions.value].sort((a,b) => {
    // 保持和后端一致的排序逻辑
    if (a.date !== b.date) return new Date(b.date) - new Date(a.date)
    if (a.sort_order !== b.sort_order) return a.sort_order - b.sort_order
    return b.id - a.id
  })

  // 5. 发送请求到后端
  await fetch('/api/transactions/reorder', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(updates)
  })
}

// 通用操作
const toggleTag = (tag) => { if(form.value.tag === tag) form.value.tag = ''; else form.value.tag = tag }
const deleteTransaction = async (id) => { if(confirm("删除记录？")) { await fetch(`/api/transactions/${id}`, { method: 'DELETE' }); await fetchData() } }
const openAccountModal = (acc = null) => { isAccountEdit.value = !!acc; editAccountId.value = acc?.id; accountForm.value = acc ? {...acc} : { name: '', type: '现金', initial_balance: '', billing_day: '', due_day: '' }; showAccountModal.value = true }
const submitAccount = async () => { if (!accountForm.value.name) return; const url = isAccountEdit.value ? `/api/accounts/${editAccountId.value}` : '/api/accounts'; const method = isAccountEdit.value ? 'PUT' : 'POST'; await fetch(url, { method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify({...accountForm.value, initial_balance: Number(accountForm.value.initial_balance)||0, billing_day: Number(accountForm.value.billing_day)||null, due_day: Number(accountForm.value.due_day)||null}) }); showAccountModal.value = false; await fetchData() }
const deleteAccount = async (id) => { if(confirm("删除账户会连带删除交易，确定？")) { await fetch(`/api/accounts/${id}`, { method: 'DELETE' }); if(selectedAccount.value?.id===id) selectedAccount.value=null; await fetchData() } }
const openCategoryModal = (type, parentId = null, catToEdit = null) => { isCatEdit.value = !!catToEdit; editCatId.value = catToEdit?.id; categoryForm.value = catToEdit ? { ...catToEdit, parent_id: catToEdit.parent_id||'' } : { name: '', type: type, parent_id: parentId||'' }; showCategoryModal.value = true }
const submitCategory = async () => { if (!categoryForm.value.name) return; const url = isCatEdit.value ? `/api/categories/${editCatId.value}` : '/api/categories'; const method = isCatEdit.value ? 'PUT' : 'POST'; await fetch(url, { method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify({...categoryForm.value, parent_id: categoryForm.value.parent_id ? Number(categoryForm.value.parent_id) : null}) }); showCategoryModal.value = false; await fetchData() }
const deleteCategory = async (id) => { if(confirm("确定删除该分类？")) { await fetch(`/api/categories/${id}`, { method: 'DELETE' }); await fetchData() } }

const shiftDate = (delta) => { const d = new Date(cursorDate.value); if (filterMode.value === 'YEAR') d.setFullYear(d.getFullYear() + delta); else if (filterMode.value === 'MONTH') d.setMonth(d.getMonth() + delta); else if (filterMode.value === 'WEEK') d.setDate(d.getDate() + delta * 7); cursorDate.value = d }
const dateRange = computed(() => { if (filterMode.value === 'ALL') return null; const d = cursorDate.value; let start, end; if (filterMode.value === 'YEAR') { start = new Date(d.getFullYear(), 0, 1); end = new Date(d.getFullYear(), 11, 31, 23, 59, 59) } else if (filterMode.value === 'MONTH') { start = new Date(d.getFullYear(), d.getMonth(), 1); end = new Date(d.getFullYear(), d.getMonth() + 1, 0, 23, 59, 59) } else if (filterMode.value === 'WEEK') { const day = d.getDay() || 7; start = new Date(d); start.setHours(0,0,0,0); start.setDate(d.getDate() - day + 1); end = new Date(start); end.setDate(start.getDate() + 6); end.setHours(23,59,59,999) } return { start, end } })
const dateLabel = computed(() => { if (filterMode.value === 'ALL') return '全部记录'; const d = cursorDate.value; const y = d.getFullYear(); const m = d.getMonth() + 1; if (filterMode.value === 'YEAR') return `${y}年`; if (filterMode.value === 'MONTH') return `${y}年 ${m}月`; if (filterMode.value === 'WEEK') { const { start, end } = dateRange.value; return `${start.getMonth()+1}.${start.getDate()} ~ ${end.getMonth()+1}.${end.getDate()} (周)` } return '' })

const filteredTransactions = computed(() => {
  let list = transactions.value
  if (selectedAccount.value) list = list.filter(t => t.account_id === selectedAccount.value.id || t.target_account_id === selectedAccount.value.id)
  if (filterMode.value !== 'ALL' && dateRange.value) { const { start, end } = dateRange.value; const s = start.getTime(); const e = end.getTime(); list = list.filter(t => { const time = new Date(t.date).getTime(); return time >= s && time <= e }) }
  // 确保按 sort_order 排序
  return list.sort((a, b) => {
     if (a.date !== b.date) return new Date(b.date) - new Date(a.date)
     if (a.sort_order !== b.sort_order) return a.sort_order - b.sort_order
     return b.id - a.id
  })
})
const periodStats = computed(() => { let i=0, e=0; filteredTransactions.value.forEach(t => { if (t.type === 'INCOME' || (t.type === 'TRANSFER' && t.target_account_id === selectedAccount.value?.id)) i += t.amount; else if (t.type === 'EXPENSE' || (t.type === 'TRANSFER' && t.account_id === selectedAccount.value?.id)) e += t.amount }); return { income: i.toFixed(2), expense: e.toFixed(2), balance: (i - e).toFixed(2) } })
const assetStats = computed(() => { let a=0, l=0; accounts.value.forEach(acc => acc.balance >=0 ? a+=acc.balance : l+=acc.balance); return { assets: a.toFixed(2), liabilities: l.toFixed(2), netWorth: (a+l).toFixed(2) } })
const groupedAccounts = computed(() => { const g={}; accounts.value.forEach(acc => { if (!g[acc.type]) g[acc.type] = { name: acc.type, accounts: [], total: 0 }; g[acc.type].accounts.push(acc); g[acc.type].total += acc.balance }); return g })
const creditStatsMap = computed(() => { const m={}; accounts.value.forEach(acc => { if (acc.type === '信用卡' && acc.billing_day) { const now = new Date(); let by = now.getFullYear(); let bm = now.getMonth(); const d = acc.billing_day; if (now.getDate() < d) bm--; const bd = new Date(by, bm, d, 23, 59, 59, 999); let s = acc.initial_balance || 0; let u = 0; transactions.value.forEach(t => { if (t.account_id !== acc.id && t.target_account_id !== acc.id) return; const td = new Date(t.date); let amt = 0; if (t.type === 'INCOME' && t.account_id === acc.id) amt = t.amount; else if (t.type === 'EXPENSE' && t.account_id === acc.id) amt = -t.amount; else if (t.type === 'TRANSFER') { if (t.account_id === acc.id) amt = -t.amount; if (t.target_account_id === acc.id) amt = t.amount } if (td <= bd) s += amt; else u += amt }); m[acc.id] = { statement: -s, unbilled: -u } } }); return m })
const expenseTree = computed(() => { const l = categories.value.filter(c => c.type === 'EXPENSE'); const m = {}; const r = []; l.forEach(c => m[c.id] = { ...c, children: [] }); l.forEach(c => { if (c.parent_id && m[c.parent_id]) m[c.parent_id].children.push(m[c.id]); else r.push(m[c.id]) }); return r })
const incomeTree = computed(() => { const l = categories.value.filter(c => c.type === 'INCOME'); const m = {}; const r = []; l.forEach(c => m[c.id] = { ...c, children: [] }); l.forEach(c => { if (c.parent_id && m[c.parent_id]) m[c.parent_id].children.push(m[c.id]); else r.push(m[c.id]) }); return r })
const availableCategoryOptions = computed(() => { const flatten = (t, l=0) => { let o=[]; t.forEach(n => { o.push({ id: n.id, name: n.name, level: l, label: '　'.repeat(l) + n.name }); if (n.children.length) o = o.concat(flatten(n.children, l + 1)) }); return o }; return flatten(form.value.type === 'EXPENSE' ? expenseTree.value : incomeTree.value) })
const parentCategoryOptions = computed(() => categories.value.filter(c => c.type === categoryForm.value.type && !c.parent_id && c.id !== editCatId.value))
const setDefaultCategory = () => { const o = availableCategoryOptions.value; form.value.category = o.length > 0 ? o[0].name : '' }
const onTypeChange = () => setDefaultCategory()

onMounted(fetchData)
</script>

<template>
  <div class="app-layout">
    <div class="sidebar">
      <div class="logo-area"><span class="logo-icon">💰</span> <span style="font-weight: bold;">我的账本</span></div>
      
      <div class="nav-item" :class="{active: activeView==='transactions'}" @click="activeView='transactions'; selectedAccount=null"><span class="icon">🏦</span> 账户交易</div>
      
      <div class="nav-item" :class="{active: activeView==='reports'}" @click="activeView='reports'; selectedAccount=null"><span class="icon">📊</span> 报表分析</div>
      
      <div class="spacer"></div>
      <div class="nav-item settings-btn" :class="{active: activeView==='settings'}" @click="activeView='settings'"><span class="icon">⚙️</span> 设置中心</div>
    </div>
    
    <div class="main-content">
      
      <div v-if="activeView === 'transactions'" class="transactions-view-container">
          <div class="transactions-sidebar">
              <h3 style="margin: 0; padding: 15px 20px; font-size: 16px; border-bottom: 1px solid #eee;">账户列表</h3>
              
              <div 
                  class="nav-item" 
                  :class="{active: activeView==='transactions' && !selectedAccount}" 
                  @click="selectedAccount=null"
              >
                  <span class="icon">📂</span> 所有交易
              </div>

              <div class="account-group" v-for="(group, type) in groupedAccounts" :key="type" style="padding: 0 10px;">
                  <div class="group-header" style="padding-left: 20px;"><span>{{ type }}</span><span>¥{{ group.total.toFixed(2) }}</span></div>
                  <div class="nav-item sub-item" v-for="acc in group.accounts" :key="acc.id" :class="{active: selectedAccount?.id===acc.id}" @click="selectedAccount=acc" style="padding-left: 20px;">
                      <div style="flex: 1;">
                          <div class="acc-row-main"><span class="acc-name">{{ acc.name }}</span><span class="acc-balance" :class="{'text-green': acc.balance<0}">{{ acc.balance.toFixed(2) }}</span></div>
                          <div v-if="acc.type==='信用卡' && creditStatsMap[acc.id]" class="credit-details">
                            <div class="cd-row"><span>本期应还:</span><span :class="{'text-warn': creditStatsMap[acc.id].statement > 0}">{{ creditStatsMap[acc.id].statement.toFixed(2) }}</span></div>
                            <div class="cd-row"><span>未出账单:</span><span>{{ creditStatsMap[acc.id].unbilled.toFixed(2) }}</span></div>
                          </div>
                      </div>
                  </div>
              </div>
          </div>

          <div class="transaction-content-area">
            <div class="top-stats">
              <div class="stat-item"><div class="stat-label">净资产</div><div class="stat-value text-blue">{{ assetStats.netWorth }}</div></div>
              <div class="stat-item"><div class="stat-label">总资产</div><div class="stat-value text-red">{{ assetStats.assets }}</div></div>
              <div class="stat-item"><div class="stat-label">总负债</div><div class="stat-value text-green">{{ assetStats.liabilities }}</div></div>
              <div style="flex:1"></div><button class="btn-record" @click="openCreateTransaction">✏️ 记一笔</button>
            </div>
            <div class="table-container">
              <div class="filter-bar">
                <div class="left-tools"><span class="current-view">{{ selectedAccount ? selectedAccount.name : '所有账户' }}</span></div>
                <div class="date-tools">
                  <div class="mode-switch"><button :class="{active: filterMode==='ALL'}" @click="filterMode='ALL'">全部</button><button :class="{active: filterMode==='YEAR'}" @click="filterMode='YEAR'">年</button><button :class="{active: filterMode==='MONTH'}" @click="filterMode='MONTH'">月</button><button :class="{active: filterMode==='WEEK'}" @click="filterMode='WEEK'">周</button></div>
                  <div class="date-nav" v-if="filterMode !== 'ALL'"><button class="nav-btn" @click="shiftDate(-1)">◀</button><span class="date-label">{{ dateLabel }}</span><button class="nav-btn" @click="shiftDate(1)">▶</button><button class="nav-btn today" @click="cursorDate=new Date()">今</button></div>
                </div>
              </div>
              <table>
                <thead><tr><th width="120">日期</th><th>分类</th><th class="text-right">流入(收)</th><th class="text-right">流出(支)</th><th>账户</th><th>备注/标签</th><th width="80">操作</th></tr></thead>
                <tbody>
                  <tr 
                    v-for="t in filteredTransactions" 
                    :key="t.id"
                    draggable="true"
                    @dragstart="onDragStart($event, t)"
                    @dragover="onDragOver($event, t)"
                    @drop="onDrop($event, t)"
                    class="draggable-row"
                  >
                    <td class="text-gray cursor-grab">{{ t.date.split('T')[0] }}</td>
                    <td>{{ t.type==='TRANSFER'?'转账':t.category }}</td>
                    <td class="text-right text-red"><span v-if="t.type==='INCOME'||(t.type==='TRANSFER'&&t.target_account_id===selectedAccount?.id)">+{{ t.amount }}</span></td>
                    <td class="text-right text-green"><span v-if="t.type==='EXPENSE'||(t.type==='TRANSFER'&&(!selectedAccount||t.account_id===selectedAccount?.id))">-{{ t.amount }}</span></td>
                    <td class="text-gray">{{ t.type==='TRANSFER'?`${t.account_name} ➜ ${t.target_account_name}`:t.account_name }}</td>
                    <td class="text-gray"><span v-if="t.tag" class="tag-badge">{{ t.tag }}</span>{{ t.note }}</td>
                    <td>
                      <button class="btn-icon" @click="openEditTransaction(t)" title="编辑">✎</button>
                      <button class="btn-icon" @click="deleteTransaction(t.id)" title="删除">🗑</button>
                    </td>
                  </tr>
                </tbody>
              </table>
              <div v-if="transactions.length===0" class="empty-state">暂无数据</div>
              <div class="table-footer" v-if="filteredTransactions.length > 0">
                <span>{{ dateLabel }} 合计：</span><span class="stat-pill income">收入: {{ periodStats.income }}</span><span class="stat-pill expense">支出: {{ periodStats.expense }}</span><span class="stat-pill balance">结余: {{ periodStats.balance }}</span>
              </div>
            </div>
          </div>
      </div>
      
      <div v-if="activeView === 'reports'" class="reports-view-container">
          <div class="reports-sidebar">
              <h3 style="margin: 0; padding: 20px; font-size: 16px; border-bottom: 1px solid #eee;">报表选项</h3>
              <div class="nav-item" :class="{active: selectedReport==='overview'}" @click="selectedReport='overview'">🧾 财务概览</div>
              <div class="nav-item" :class="{active: selectedReport==='category'}" @click="selectedReport='category'">📈 分类收支统计</div>
              <div class="nav-item" :class="{active: selectedReport==='trend'}" @click="selectedReport='trend'">📉 趋势分析</div>
          </div>
          <div class="reports-display">
              <h2 style="padding: 20px 30px; margin: 0; border-bottom: 1px solid #eee;">
                  {{ selectedReport === 'overview' ? '财务概览' : selectedReport === 'category' ? '分类收支统计' : '收支趋势' }}
              </h2>
              <div style="padding: 30px; color: #666;">
                  <p>这里是报表显示区域。根据您在左侧报告选项栏（第二栏）选择的类型显示具体内容。</p>
                  <p style="margin-top: 30px; color: #999;">报表功能正在开发中...</p>
              </div>
          </div>
      </div>
      
      <div v-if="activeView === 'settings'" class="view-container settings-view">
        <h2 style="padding: 20px 30px; margin: 0; border-bottom: 1px solid #eee;">设置中心</h2>
        <div class="settings-tabs"><button :class="{active: settingsTab==='accounts'}" @click="settingsTab='accounts'">账户管理</button><button :class="{active: settingsTab==='categories'}" @click="settingsTab='categories'">分类管理</button></div>
        <div v-if="settingsTab === 'accounts'" class="settings-panel"><div class="settings-inner"><div class="panel-header"><h3>所有账户</h3><button class="btn-sm primary" @click="openAccountModal(null)">+ 新建账户</button></div><div class="account-list"><div class="account-row header"><span>名称</span><span>类型</span><span class="text-right">余额</span><span class="text-right">操作</span></div><div class="account-row" v-for="acc in accounts" :key="acc.id"><div class="col-name"><span style="font-weight:500;font-size:15px">{{ acc.name }}</span><span v-if="acc.type==='信用卡'" style="font-size:12px;color:#999;margin-top:2px">账单日:{{ acc.billing_day||'-' }} / 还款日:{{ acc.due_day||'-' }}</span></div><div><span class="badge">{{ acc.type }}</span></div><div class="text-right bold" :class="{'text-green': acc.balance<0}">{{ acc.balance.toFixed(2) }}</div><div class="action-btns"><button class="btn-sm" @click="openAccountModal(acc)">编辑</button><button class="btn-sm danger" @click="deleteAccount(acc.id)">删除</button></div></div></div></div></div>
        <div v-if="settingsTab === 'categories'" class="settings-panel"><div class="settings-inner">
          <div class="panel-section"><div class="panel-header"><h3>支出分类</h3><button class="btn-sm primary" @click="openCategoryModal('EXPENSE')">+ 添加主分类</button></div><div class="category-tree"><div v-for="parent in expenseTree" :key="parent.id" class="tree-node"><div class="node-content parent"><span class="node-name">{{ parent.name }}</span><div class="node-actions"><button class="btn-text" @click="openCategoryModal('EXPENSE', parent.id)">+子类</button><button class="btn-text" @click="openCategoryModal('EXPENSE', null, parent)">编辑</button><button class="btn-text danger" @click="deleteCategory(parent.id)">删除</button></div></div><div v-if="parent.children.length" class="node-children"><div v-for="child in parent.children" :key="child.id" class="node-content child"><span class="node-name">{{ child.name }}</span><div class="node-actions"><button class="btn-text" @click="openCategoryModal('EXPENSE', parent.id, child)">编辑</button><button class="btn-text danger" @click="deleteCategory(child.id)">×</button></div></div></div></div></div></div>
          <div class="panel-section" style="margin-top:40px"><div class="panel-header"><h3>收入分类</h3><button class="btn-sm primary" @click="openCategoryModal('INCOME')">+ 添加主分类</button></div><div class="category-tree"><div v-for="parent in incomeTree" :key="parent.id" class="tree-node"><div class="node-content parent income"><span class="node-name">{{ parent.name }}</span><div class="node-actions"><button class="btn-text" @click="openCategoryModal('INCOME', parent.id)">+子类</button><button class="btn-text" @click="openCategoryModal('INCOME', null, parent)">编辑</button><button class="btn-text danger" @click="deleteCategory(parent.id)">删除</button></div></div><div v-if="parent.children.length" class="node-children"><div v-for="child in parent.children" :key="child.id" class="node-content child"><span class="node-name">{{ child.name }}</span><div class="node-actions"><button class="btn-text" @click="openCategoryModal('INCOME', parent.id, child)">编辑</button><button class="btn-text danger" @click="deleteCategory(child.id)">×</button></div></div></div></div></div></div>
        </div></div>
      </div>
    </div>
    
    <div class="modal-overlay" v-if="showRecordModal" @click.self="showRecordModal=false"><div class="modal-card"><h3>{{ isTransactionEdit ? '✏️ 编辑交易' : '📝 记一笔' }}</h3><div class="type-tabs"><label :class="{active: form.type==='EXPENSE'}"><input type="radio" value="EXPENSE" v-model="form.type" @change="onTypeChange" hidden> 支出</label><label :class="{active: form.type==='INCOME'}"><input type="radio" value="INCOME" v-model="form.type" @change="onTypeChange" hidden> 收入</label><label :class="{active: form.type==='TRANSFER'}"><input type="radio" value="TRANSFER" v-model="form.type" hidden> 转账</label></div><div class="modal-form"><div class="row"><input type="date" v-model="form.date"><input type="number" v-model="form.amount" placeholder="金额"></div><div class="row"><div style="flex:1;display:flex;flex-direction:column"><select v-model="form.account_id"><option value="" disabled>{{form.type==='TRANSFER'?'转出账户':'记账账户'}}</option><option v-for="acc in accounts" :key="acc.id" :value="acc.id">{{ acc.name }}</option></select></div><div v-if="form.type==='TRANSFER'" style="flex:1"><select v-model="form.target_account_id"><option value="" disabled>转入账户</option><option v-for="acc in accounts" :key="acc.id" :value="acc.id">{{ acc.name }}</option></select></div><div v-if="form.type==='EXPENSE' && !isTransactionEdit" style="flex:1"><select v-model="form.fund_account_id" style="color:#2c3e50;border-color:#3498db"><option value="">默认 (余额支付)</option><optgroup label="实际扣款账户"><option v-for="acc in accounts.filter(a=>a.id!==form.account_id)" :key="acc.id" :value="acc.id">扣: {{ acc.name }}</option></optgroup></select></div></div><div v-if="form.type!=='TRANSFER'" class="row"><select v-model="form.category"><option value="" disabled>选择分类</option><option v-for="opt in availableCategoryOptions" :key="opt.id" :value="opt.name" v-html="opt.label"></option></select></div><div class="row tag-row" style="margin-top:10px"><label style="margin-right:10px;font-size:0.9em;color:#666">标签:</label><div class="tags-wrapper"><span v-for="tag in commonTags" :key="tag" class="tag-chip" :class="{active: form.tag===tag}" @click="toggleTag(tag)">{{ tag }}</span></div></div><input v-model="form.note" placeholder="备注..." style="width:100%;margin-top:10px"></div><div class="modal-actions"><button class="btn-modal btn-cancel" @click="showRecordModal=false">取消</button><button v-if="!isTransactionEdit" class="btn-modal btn-continue" @click="submitTransaction(true)">保存并继续</button><button class="btn-modal btn-save" @click="submitTransaction(false)">保存记录</button></div></div></div>
    <div class="modal-overlay" v-if="showAccountModal" @click.self="showAccountModal=false"><div class="modal-card"><h3>{{ isAccountEdit ? '🔧 编辑账户' : '💳 新建账户' }}</h3><div class="modal-form"><label>名称</label><input v-model="accountForm.name"><div class="row" style="margin-top:10px"><div style="flex:1"><label>类型</label><select v-model="accountForm.type"><option>现金</option><option>储蓄卡</option><option>信用卡</option><option>支付宝/微信</option></select></div><div style="flex:1"><label>初始余额</label><input type="number" v-model="accountForm.initial_balance"></div></div><div v-if="accountForm.type==='信用卡'" class="row" style="margin-top:10px;background:#f9f9f9;padding:10px;border-radius:6px"><div style="flex:1"><label>账单日</label><input type="number" v-model="accountForm.billing_day"></div><div style="flex:1"><label>还款日</label><input type="number" v-model="accountForm.due_day"></div></div></div><div class="modal-actions"><button class="btn-modal btn-cancel" @click="showAccountModal=false">取消</button><button class="btn-modal btn-save" @click="submitAccount">确认</button></div></div></div>
    <div class="modal-overlay" v-if="showCategoryModal" @click.self="showCategoryModal=false"><div class="modal-card"><h3>{{ isCatEdit ? '🔧 编辑分类' : '➕ 新增分类' }}</h3><div class="modal-form"><label>分类名称</label><input v-model="categoryForm.name"><label style="margin-top:10px">父级分类</label><select v-model="categoryForm.parent_id"><option value="">无 (主分类)</option><option v-for="p in parentCategoryOptions" :key="p.id" :value="p.id">{{ p.name }}</option></select></div><div class="modal-actions"><button class="btn-modal btn-cancel" @click="showCategoryModal=false">取消</button><button class="btn-modal btn-save" @click="submitCategory">保存</button></div></div></div>
  </div>
</template>

<style>
/* 样式部分 */
body { margin: 0; font-family: -apple-system, sans-serif; background-color: #f0f0f0; color: #333; }
.app-layout { display: flex; height: 100vh; width: 100vw; }
/* [修改 1]: 第一栏变窄 */
.sidebar { width: 180px; background: #f7f7f7; border-right: 1px solid #ddd; display: flex; flex-direction: column; }
.main-content { flex: 1; display: flex; flex-direction: column; background: #fff; overflow: hidden; }
.view-container { display: flex; flex-direction: column; height: 100%; }
.filter-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; background: #fff; border-bottom: 1px solid #eee; padding-bottom: 15px; }
.current-view { font-size: 18px; font-weight: bold; }
.date-tools { display: flex; align-items: center; gap: 15px; }
.mode-switch { display: flex; background: #f0f0f0; border-radius: 6px; padding: 2px; }
.mode-switch button { border: none; background: none; padding: 4px 12px; font-size: 13px; cursor: pointer; border-radius: 4px; color: #666; }
.mode-switch button.active { background: #fff; color: #3498db; font-weight: bold; box-shadow: 0 1px 2px rgba(0,0,0,0.1); }
.date-nav { display: flex; align-items: center; gap: 8px; font-size: 14px; color: #555; }
.nav-btn { border: 1px solid #ddd; background: white; border-radius: 4px; cursor: pointer; padding: 2px 8px; font-size: 12px; } .nav-btn:hover { background: #f9f9f9; } .nav-btn.today { font-weight: bold; color: #3498db; }
.date-label { min-width: 100px; text-align: center; font-weight: 500; }
.table-footer { padding: 10px 15px; background: #fafafa; border-top: 2px solid #eee; display: flex; gap: 15px; font-size: 13px; font-weight: bold; align-items: center; }
.stat-pill { padding: 3px 8px; border-radius: 4px; }
.stat-pill.income { background: #fdedec; color: #e74c3c; } .stat-pill.expense { background: #eafaf1; color: #27ae60; } .stat-pill.balance { background: #ebf5fb; color: #3498db; }
.top-stats { height: 80px; padding: 0 30px; border-bottom: 1px solid #eee; display: flex; align-items: center; gap: 40px; background: #fafafa; }
.stat-item { display: flex; flex-direction: column; gap: 5px; } .stat-label { font-size: 12px; color: #888; } .stat-value { font-size: 20px; font-weight: bold; }
.btn-record { padding: 8px 20px; background: #3498db; color: white; border: none; border-radius: 20px; cursor: pointer; }
.table-container { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; }
.settings-view { background: #f9f9f9; }
.settings-tabs { display: flex; padding: 20px 30px 0; gap: 10px; border-bottom: 1px solid #ddd; background: white; }
.settings-tabs button { padding: 10px 20px; background: none; border: none; border-bottom: 3px solid transparent; cursor: pointer; font-size: 15px; color: #666; } .settings-tabs button.active { border-color: #3498db; color: #3498db; font-weight: bold; }
.settings-panel { flex: 1; overflow-y: auto; width: 100%; box-sizing: border-box; }
.settings-inner { max-width: 800px; margin: 0 auto; padding: 30px; }
.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.btn-sm { padding: 6px 12px; border-radius: 4px; border: none; cursor: pointer; font-size: 13px; margin-left: 5px; } .btn-sm.primary { background: #3498db; color: white; } .btn-sm.danger { background: #fff0f0; color: #e74c3c; }
.account-list { background: white; border: 1px solid #eee; border-radius: 8px; overflow: hidden; }
.account-row { display: grid; grid-template-columns: 3fr 1fr 1.5fr 110px; gap: 15px; padding: 15px; border-bottom: 1px solid #eee; align-items: center; }
.account-row.header { background: #fafafa; font-weight: bold; color: #888; font-size: 13px; }
.col-name { display: flex; flex-direction: column; overflow: hidden; }
.action-btns { display: flex; justify-content: flex-end; gap: 5px; }
.badge { background: #eee; padding: 2px 8px; border-radius: 10px; font-size: 12px; color: #666; }
.category-tree { display: flex; flex-direction: column; gap: 10px; }
.tree-node { background: white; border: 1px solid #eee; border-radius: 8px; overflow: hidden; }
.node-content { display: flex; justify-content: space-between; align-items: center; padding: 10px 15px; }
.node-content.parent { background: #fbfbfb; font-weight: 500; } .node-content.parent.income { border-left: 4px solid #e74c3c; } .node-content.parent:not(.income) { border-left: 4px solid #27ae60; }
.node-content.child { border-top: 1px solid #f5f5f5; padding-left: 30px; font-size: 0.95em; color: #666; }
.node-actions { display: flex; gap: 10px; opacity: 0; transition: opacity 0.2s; } .node-content:hover .node-actions { opacity: 1; }
.btn-text { background: none; border: none; color: #3498db; cursor: pointer; font-size: 12px; padding: 0; } .btn-text.danger { color: #e74c3c; }
.modal-overlay { position: fixed; top:0; left:0; width:100%; height:100%; background: rgba(0,0,0,0.4); display: flex; justify-content: center; align-items: center; z-index: 999; }
.modal-card { background: white; padding: 25px; border-radius: 10px; width: 400px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); }
.modal-form label { font-size: 0.9em; font-weight: bold; color: #555; margin-bottom: 3px; display: block; margin-top: 10px; }
.modal-form input, .modal-form select { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }
.type-tabs { display: flex; border: 1px solid #3498db; border-radius: 6px; overflow: hidden; margin-bottom: 20px; }
.type-tabs label { flex: 1; text-align: center; padding: 8px; cursor: pointer; color: #3498db; } .type-tabs label.active { background: #3498db; color: white; }
.modal-form .row { display: flex; gap: 10px; margin-top: 0; align-items: center; }
.modal-actions { margin-top: 25px; padding-top: 20px; border-top: 1px solid #f0f0f0; display: flex; gap: 10px; justify-content: flex-end; }
.btn-modal { padding: 10px 18px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; border: none; transition: all 0.2s ease; outline: none; }
.btn-cancel { background-color: #f5f7fa; color: #666; } .btn-cancel:hover { background-color: #e4e7ed; color: #333; }
.btn-save { background: linear-gradient(135deg, #3498db, #2980b9); color: white; box-shadow: 0 4px 10px rgba(52, 152, 219, 0.3); } .btn-save:hover { transform: translateY(-2px); box-shadow: 0 6px 15px rgba(52, 152, 219, 0.4); }
.btn-continue { background-color: #eafaf1; color: #27ae60; border: 1px solid #27ae60; } .btn-continue:hover { background-color: #d5f5e3; }
.tag-row { flex-wrap: wrap; } .tags-wrapper { display: flex; gap: 8px; flex-wrap: wrap; }
.tag-chip { background: #f0f0f0; color: #666; padding: 4px 12px; border-radius: 20px; font-size: 12px; cursor: pointer; border: 1px solid transparent; } .tag-chip:hover { background: #e0e0e0; } .tag-chip.active { background: #e8f4fc; color: #3498db; border-color: #3498db; font-weight: bold; }
.tag-badge { background: #e8f4fc; color: #3498db; padding: 2px 6px; border-radius: 4px; font-size: 11px; margin-right: 5px; border: 1px solid #d6eaf8; }
.nav-item { padding: 10px 20px; cursor: pointer; display: flex; align-items: center; gap: 10px; color: #555; } .nav-item:hover { background: #eaeaea; } .nav-item.active { background: #e0e0e0; color: #000; font-weight: 500; border-left: 3px solid #3498db; }
/* 针对第二栏的子项样式，取消了左侧额外的 padding，现在由模板中的 inline style 控制 */
.nav-item.sub-item { flex-direction: column; align-items: flex-start; gap: 0; padding-top: 8px; padding-bottom: 8px; }
.acc-row-main { display: flex; justify-content: space-between; width: 100%; align-items: center; }
.acc-name { 
    /* 确保账户名不会太长而挤压余额 */
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    /* 增加账户名和余额之间的最小间距 */
    margin-right: 15px; /* 增加间距 */
    max-width: 60%; /* 限制账户名最大宽度，为余额留出更多空间 */
}
/* [修改 3]: 信用卡详情左右并排显示 */
.credit-details { 
    background: #fff; 
    margin-top: 6px; 
    padding: 6px 10px; 
    border-radius: 6px; 
    border: 1px solid #eee; 
    width: 100%; 
    box-sizing: border-box; 
    display: flex; /* 启用 Flex 布局 */
    gap: 15px; /* 增加两组信息之间的间距 */
    justify-content: space-between;
}
.cd-row { 
    display: flex; 
    justify-content: space-between; 
    font-size: 11px; 
    color: #7f8c8d; 
    margin-bottom: 0; /* 消除垂直间距 */
    flex: 1; /* 让两组信息平分空间 */
} 
.text-warn { color: #e67e22; font-weight: bold; }
.group-header { padding: 5px 20px; font-size: 12px; color: #999; display: flex; justify-content: space-between; margin-top: 10px; }
.text-right { text-align: right; } .text-red { color: #e74c3c; } .text-green { color: #27ae60; } .text-blue { color: #3498db; } .text-gray { color: #999; } .spacer { flex: 1; }
table { width: 100%; border-collapse: collapse; font-size: 13px; } th { text-align: left; padding: 10px; border-bottom: 1px solid #eee; color: #888; } td { padding: 12px 10px; border-bottom: 1px solid #f5f5f5; }
.btn-icon { border: none; background: none; opacity: 0.3; cursor: pointer; } .btn-icon:hover { opacity: 1; color: red; }
.empty-state { text-align: center; padding: 40px; color: #999; }
/* 新增：拖动样式 */
.cursor-grab { cursor: grab; }
.draggable-row { cursor: grab; transition: background 0.2s; }
.draggable-row:active { cursor: grabbing; }
.dragging-row { opacity: 0.5; background: #e8f4fc; }

/* 交易视图的三栏布局样式 (整体三栏中的第二栏和第三栏) */
.transactions-view-container { 
    display: flex; 
    height: 100%; 
    flex: 1; 
    background: #f9f9f9; 
    flex-direction: row; 
}
/* [修改 2]: 第二栏加宽 */
.transactions-sidebar { 
    width: 260px; /* 第二栏的宽度 */
    background: #fff; 
    border-right: 1px solid #eee; 
    flex-shrink: 0; 
    overflow-y: auto;
}
.transaction-content-area {
    flex: 1; /* 第三栏占据剩余空间 */
    display: flex; 
    flex-direction: column;
    overflow: hidden;
    background: white;
}
/* 调整交易侧边栏的导航项样式以匹配主侧边栏 */
.transactions-sidebar .nav-item {
    padding: 10px 20px;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 10px;
    color: #555;
    border-left: 3px solid transparent; 
}
.transactions-sidebar .nav-item:hover { background: #eaeaea; } 
.transactions-sidebar .nav-item.active { background: #e0e0e0; color: #000; font-weight: 500; border-left: 3px solid #3498db; }

/* 报表视图的三栏布局样式 */
.reports-view-container { 
    display: flex; 
    height: 100%; 
    flex: 1; 
    background: #f9f9f9; 
    flex-direction: row; 
}
/* [修改 2]: 报表第二栏加宽 */
.reports-sidebar { 
    width: 260px; 
    background: #fff; 
    border-right: 1px solid #eee; 
    flex-shrink: 0; 
    display: flex;
    flex-direction: column;
}
.reports-display { 
    flex: 1; 
    background: white; 
    overflow-y: auto; 
}
/* 调整报表侧边栏的导航项样式以匹配主侧边栏 */
.reports-sidebar .nav-item {
    padding: 10px 20px;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 10px;
    color: #555;
    border-left: 3px solid transparent; 
}
.reports-sidebar .nav-item:hover { background: #eaeaea; } 
.reports-sidebar .nav-item.active { background: #e0e0e0; color: #000; font-weight: 500; border-left: 3px solid #3498db; }
</style>
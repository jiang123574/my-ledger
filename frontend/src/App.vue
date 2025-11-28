<script setup>
import { ref, onMounted, computed } from 'vue'

// --- 状态 ---
const activeView = ref('transactions'); const settingsTab = ref('accounts')
const accounts = ref([]); const categories = ref([]); const transactions = ref([])
const selectedAccount = ref(null)

// 模态框控制
const showRecordModal = ref(false)
const showAccountModal = ref(false)
const showCategoryModal = ref(false) // 新增：分类编辑弹窗

// 表单数据
const form = ref({ type: 'EXPENSE', date: new Date().toISOString().split('T')[0], amount: '', category: '', note: '', account_id: '', target_account_id: '' })
const isAccountEdit = ref(false); const editAccountId = ref(null)
const accountForm = ref({ name: '', type: '现金', initial_balance: '', billing_day: '', due_day: '' })

// 分类表单
const isCatEdit = ref(false); const editCatId = ref(null)
const categoryForm = ref({ name: '', type: 'EXPENSE', parent_id: '' })

// --- API ---
const fetchData = async () => {
  try {
    const [acc, cat, trans] = await Promise.all([
      fetch('/api/accounts').then(r => r.json()),
      fetch('/api/categories').then(r => r.json()),
      fetch('/api/transactions').then(r => r.json())
    ])
    accounts.value = acc; categories.value = cat; transactions.value = trans
    if (acc.length > 0 && !form.value.account_id) form.value.account_id = acc[0].id
    setDefaultCategory()
  } catch (e) { console.error(e) }
}

const submitTransaction = async () => {
  if (!form.value.amount || !form.value.account_id) return alert('请补全信息')
  if (form.value.type !== 'TRANSFER' && !form.value.category) return alert('请选择分类')
  
  const payload = {
    ...form.value,
    date: new Date(form.value.date).toISOString(),
    amount: Number(form.value.amount),
    account_id: Number(form.value.account_id),
    target_account_id: form.value.target_account_id ? Number(form.value.target_account_id) : null,
    category: form.value.type === 'TRANSFER' ? '转账' : form.value.category
  }
  const res = await fetch('/api/transactions', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) })
  if(res.ok) { form.value.amount = ''; form.value.note = ''; showRecordModal.value = false; await fetchData() }
}

// 账户操作
const openAccountModal = (acc = null) => {
  isAccountEdit.value = !!acc; editAccountId.value = acc?.id
  accountForm.value = acc ? { ...acc, billing_day: acc.billing_day||'', due_day: acc.due_day||'' } 
                          : { name: '', type: '现金', initial_balance: '', billing_day: '', due_day: '' }
  showAccountModal.value = true
}
const submitAccount = async () => {
  if (!accountForm.value.name) return
  const payload = { ...accountForm.value, initial_balance: Number(accountForm.value.initial_balance)||0, billing_day: Number(accountForm.value.billing_day)||null, due_day: Number(accountForm.value.due_day)||null }
  const url = isAccountEdit.value ? `/api/accounts/${editAccountId.value}` : '/api/accounts'
  const method = isAccountEdit.value ? 'PUT' : 'POST'
  await fetch(url, { method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) })
  showAccountModal.value = false; await fetchData()
}
const deleteAccount = async (id) => { if(confirm("删除账户会连带删除交易，确定？")) { await fetch(`/api/accounts/${id}`, { method: 'DELETE' }); await fetchData() } }

// 分类操作 (新增/修改)
const openCategoryModal = (type, parentId = null, catToEdit = null) => {
  isCatEdit.value = !!catToEdit; editCatId.value = catToEdit?.id
  if (catToEdit) {
    categoryForm.value = { name: catToEdit.name, type: catToEdit.type, parent_id: catToEdit.parent_id || '' }
  } else {
    categoryForm.value = { name: '', type: type, parent_id: parentId || '' }
  }
  showCategoryModal.value = true
}

const submitCategory = async () => {
  if (!categoryForm.value.name) return
  const payload = { 
    name: categoryForm.value.name, 
    type: categoryForm.value.type, 
    parent_id: categoryForm.value.parent_id ? Number(categoryForm.value.parent_id) : null 
  }
  const url = isCatEdit.value ? `/api/categories/${editCatId.value}` : '/api/categories'
  const method = isCatEdit.value ? 'PUT' : 'POST'
  
  await fetch(url, { method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) })
  showCategoryModal.value = false; await fetchData()
}

const deleteCategory = async (id) => { if(confirm("确定删除？")) { await fetch(`/api/categories/${id}`, { method: 'DELETE' }); await fetchData() } }
const deleteTransaction = async (id) => { if(confirm("确定删除？")) { await fetch(`/api/transactions/${id}`, { method: 'DELETE' }); await fetchData() } }

// --- 计算属性 ---
const groupedAccounts = computed(() => {
  const groups = {}
  accounts.value.forEach(acc => {
    if (!groups[acc.type]) groups[acc.type] = { name: acc.type, accounts: [], total: 0 }
    groups[acc.type].accounts.push(acc)
    groups[acc.type].total += acc.balance
  })
  return groups
})
const assetStats = computed(() => {
  let a=0, l=0; accounts.value.forEach(acc => acc.balance >=0 ? a+=acc.balance : l+=acc.balance)
  return { assets: a.toFixed(2), liabilities: l.toFixed(2), netWorth: (a+l).toFixed(2) }
})
const filteredTransactions = computed(() => {
  let list = transactions.value
  if (selectedAccount.value) list = list.filter(t => t.account_id === selectedAccount.value.id || t.target_account_id === selectedAccount.value.id)
  return list
})

// 分类树形处理
const buildTree = (type) => {
  const list = categories.value.filter(c => c.type === type)
  const map = {}; const roots = []
  list.forEach(c => map[c.id] = { ...c, children: [] })
  list.forEach(c => {
    if (c.parent_id && map[c.parent_id]) map[c.parent_id].children.push(map[c.id])
    else roots.push(map[c.id])
  })
  return roots
}
const expenseTree = computed(() => buildTree('EXPENSE'))
const incomeTree = computed(() => buildTree('INCOME'))

// 扁平化树用于下拉选择 (记账弹窗)
const flattenOptions = (tree, level = 0) => {
  let opts = []
  tree.forEach(node => {
    opts.push({ id: node.id, name: node.name, level, label: '　'.repeat(level) + node.name })
    if (node.children.length > 0) opts = opts.concat(flattenOptions(node.children, level + 1))
  })
  return opts
}
const availableCategoryOptions = computed(() => {
  const tree = form.value.type === 'EXPENSE' ? expenseTree.value : incomeTree.value
  return flattenOptions(tree)
})
// 仅父级分类 (用于分类编辑弹窗选择父级)
const parentCategoryOptions = computed(() => {
  // 只能选择同一层级的作为父级，且不能选自己（编辑时）
  return categories.value.filter(c => c.type === categoryForm.value.type && !c.parent_id && c.id !== editCatId.value)
})

const setDefaultCategory = () => {
  const opts = availableCategoryOptions.value
  form.value.category = opts.length > 0 ? opts[0].name : ''
}
const onTypeChange = () => setDefaultCategory()

onMounted(fetchData)
</script>

<template>
  <div class="app-layout">
    <div class="sidebar">
      <div class="logo-area"><span class="logo-icon">💰</span> <span style="font-weight: bold;">我的账本</span></div>
      <div class="nav-item" :class="{active: activeView==='transactions' && !selectedAccount}" @click="activeView='transactions'; selectedAccount=null"><span class="icon">📂</span> 所有交易</div>
      <div class="account-group" v-for="(group, type) in groupedAccounts" :key="type">
        <div class="group-header"><span>{{ type }}</span><span>¥{{ group.total.toFixed(2) }}</span></div>
        <div class="nav-item sub-item" v-for="acc in group.accounts" :key="acc.id" :class="{active: selectedAccount?.id===acc.id}" @click="activeView='transactions'; selectedAccount=acc">
          <span class="acc-name">{{ acc.name }}</span><span class="acc-balance" :class="{'text-red': acc.balance<0}">{{ acc.balance.toFixed(2) }}</span>
        </div>
      </div>
      <div class="spacer"></div>
      <div class="nav-item settings-btn" :class="{active: activeView==='settings'}" @click="activeView='settings'"><span class="icon">⚙️</span> 设置中心</div>
    </div>

    <div class="main-content">
      <div v-if="activeView === 'transactions'" class="view-container">
        <div class="top-stats">
          <div class="stat-item"><div class="stat-label">净资产</div><div class="stat-value text-blue">{{ assetStats.netWorth }}</div></div>
          <div class="stat-item"><div class="stat-label">总资产</div><div class="stat-value text-green">{{ assetStats.assets }}</div></div>
          <div class="stat-item"><div class="stat-label">总负债</div><div class="stat-value text-red">{{ assetStats.liabilities }}</div></div>
          <div style="flex:1"></div>
          <button class="btn-record" @click="showRecordModal=true">✏️ 记一笔</button>
        </div>
        <div class="table-container">
          <div class="filter-bar"><span class="current-view">{{ selectedAccount ? selectedAccount.name : '所有交易' }}</span></div>
          <table>
            <thead><tr><th width="120">日期</th><th>分类</th><th class="text-right">流入</th><th class="text-right">流出</th><th>账户</th><th>备注</th><th width="50"></th></tr></thead>
            <tbody>
              <tr v-for="t in filteredTransactions" :key="t.id">
                <td class="text-gray">{{ t.date.split('T')[0] }}</td>
                <td>{{ t.type==='TRANSFER'?'转账':t.category }}</td>
                <td class="text-right text-green"><span v-if="t.type==='INCOME'||(t.type==='TRANSFER'&&t.target_account_id===selectedAccount?.id)">+{{ t.amount }}</span></td>
                <td class="text-right text-red"><span v-if="t.type==='EXPENSE'||(t.type==='TRANSFER'&&(!selectedAccount||t.account_id===selectedAccount?.id))">-{{ t.amount }}</span></td>
                <td class="text-gray">{{ t.type==='TRANSFER'?`${t.account_name} ➜ ${t.target_account_name}`:t.account_name }}</td>
                <td class="text-gray">{{ t.note }}</td>
                <td><button class="btn-icon" @click="deleteTransaction(t.id)">🗑</button></td>
              </tr>
            </tbody>
          </table>
          <div v-if="transactions.length===0" class="empty-state">暂无数据</div>
        </div>
      </div>

      <div v-if="activeView === 'settings'" class="view-container settings-view">
        <h2 style="padding: 20px 30px; margin: 0; border-bottom: 1px solid #eee;">设置中心</h2>
        <div class="settings-tabs">
          <button :class="{active: settingsTab==='accounts'}" @click="settingsTab='accounts'">账户管理</button>
          <button :class="{active: settingsTab==='categories'}" @click="settingsTab='categories'">分类管理</button>
        </div>

        <div v-if="settingsTab === 'accounts'" class="settings-panel">
          <div class="panel-header"><h3>所有账户</h3><button class="btn-sm primary" @click="openAccountModal(null)">+ 新建账户</button></div>
          <div class="account-list">
            <div class="account-row header"><span>名称</span><span>类型</span><span class="text-right">余额</span><span class="text-right">操作</span></div>
            <div class="account-row" v-for="acc in accounts" :key="acc.id">
              <div style="display:flex;flex-direction:column;flex:1"><span style="font-weight:500">{{ acc.name }}</span><span v-if="acc.type==='信用卡'" style="font-size:0.8em;color:#999">账单日:{{ acc.billing_day||'-' }} / 还款日:{{ acc.due_day||'-' }}</span></div>
              <span style="flex:1"><span class="badge">{{ acc.type }}</span></span>
              <span class="text-right bold" style="flex:1">{{ acc.balance }}</span>
              <div class="text-right action-btns" style="flex:1"><button class="btn-sm" @click="openAccountModal(acc)">编辑</button><button class="btn-sm danger" @click="deleteAccount(acc.id)">删除</button></div>
            </div>
          </div>
        </div>

        <div v-if="settingsTab === 'categories'" class="settings-panel">
          <div class="panel-section">
            <div class="panel-header"><h3>支出分类</h3><button class="btn-sm primary" @click="openCategoryModal('EXPENSE')">+ 添加主分类</button></div>
            <div class="category-tree">
              <div v-for="parent in expenseTree" :key="parent.id" class="tree-node">
                <div class="node-content parent">
                  <span class="node-name">{{ parent.name }}</span>
                  <div class="node-actions">
                    <button class="btn-text" @click="openCategoryModal('EXPENSE', parent.id)">+子类</button>
                    <button class="btn-text" @click="openCategoryModal('EXPENSE', null, parent)">编辑</button>
                    <button class="btn-text danger" @click="deleteCategory(parent.id)">删除</button>
                  </div>
                </div>
                <div v-if="parent.children.length" class="node-children">
                  <div v-for="child in parent.children" :key="child.id" class="node-content child">
                    <span class="node-name">{{ child.name }}</span>
                    <div class="node-actions">
                      <button class="btn-text" @click="openCategoryModal('EXPENSE', parent.id, child)">编辑</button>
                      <button class="btn-text danger" @click="deleteCategory(child.id)">×</button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div class="panel-section" style="margin-top: 40px;">
            <div class="panel-header"><h3>收入分类</h3><button class="btn-sm primary" @click="openCategoryModal('INCOME')">+ 添加主分类</button></div>
            <div class="category-tree">
              <div v-for="parent in incomeTree" :key="parent.id" class="tree-node">
                <div class="node-content parent income">
                  <span class="node-name">{{ parent.name }}</span>
                  <div class="node-actions">
                    <button class="btn-text" @click="openCategoryModal('INCOME', parent.id)">+子类</button>
                    <button class="btn-text" @click="openCategoryModal('INCOME', null, parent)">编辑</button>
                    <button class="btn-text danger" @click="deleteCategory(parent.id)">删除</button>
                  </div>
                </div>
                <div v-if="parent.children.length" class="node-children">
                  <div v-for="child in parent.children" :key="child.id" class="node-content child">
                    <span class="node-name">{{ child.name }}</span>
                    <div class="node-actions">
                      <button class="btn-text" @click="openCategoryModal('INCOME', parent.id, child)">编辑</button>
                      <button class="btn-text danger" @click="deleteCategory(child.id)">×</button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="modal-overlay" v-if="showRecordModal" @click.self="showRecordModal = false">
      <div class="modal-card">
        <h3>📝 记一笔</h3>
        <div class="type-tabs">
          <label :class="{active: form.type==='EXPENSE'}"><input type="radio" value="EXPENSE" v-model="form.type" @change="onTypeChange" hidden> 支出</label>
          <label :class="{active: form.type==='INCOME'}"><input type="radio" value="INCOME" v-model="form.type" @change="onTypeChange" hidden> 收入</label>
          <label :class="{active: form.type==='TRANSFER'}"><input type="radio" value="TRANSFER" v-model="form.type" hidden> 转账</label>
        </div>
        <div class="modal-form">
          <div class="row"><input type="date" v-model="form.date"><input type="number" v-model="form.amount" placeholder="金额"></div>
          <div class="row">
            <select v-model="form.account_id"><option value="" disabled>账户</option><option v-for="acc in accounts" :key="acc.id" :value="acc.id">{{ acc.name }}</option></select>
            <select v-if="form.type === 'TRANSFER'" v-model="form.target_account_id"><option value="" disabled>转入账户</option><option v-for="acc in accounts" :key="acc.id" :value="acc.id">{{ acc.name }}</option></select>
            
            <select v-if="form.type !== 'TRANSFER'" v-model="form.category">
              <option value="" disabled>选择分类</option>
              <option v-for="opt in availableCategoryOptions" :key="opt.id" :value="opt.name" v-html="opt.label"></option>
            </select>
          </div>
          <input v-model="form.note" placeholder="备注..." style="width:100%;margin-top:10px">
        </div>
        <div class="modal-actions"><button class="btn-modal btn-cancel" @click="showRecordModal=false">取消</button><button class="btn-modal btn-save" @click="submitTransaction">保存记录</button></div>
      </div>
    </div>

    <div class="modal-overlay" v-if="showAccountModal" @click.self="showAccountModal = false">
      <div class="modal-card">
        <h3>{{ isAccountEdit ? '🔧 编辑账户' : '💳 新建账户' }}</h3>
        <div class="modal-form">
          <label>名称</label><input v-model="accountForm.name">
          <div class="row" style="margin-top:10px">
            <div style="flex:1"><label>类型</label><select v-model="accountForm.type"><option>现金</option><option>储蓄卡</option><option>信用卡</option><option>支付宝/微信</option></select></div>
            <div style="flex:1"><label>初始余额</label><input type="number" v-model="accountForm.initial_balance"></div>
          </div>
          <div v-if="accountForm.type==='信用卡'" class="row" style="margin-top:10px;background:#f9f9f9;padding:10px;border-radius:6px">
            <div style="flex:1"><label>账单日</label><input type="number" v-model="accountForm.billing_day" placeholder="日"></div>
            <div style="flex:1"><label>还款日</label><input type="number" v-model="accountForm.due_day" placeholder="日"></div>
          </div>
        </div>
        <div class="modal-actions"><button class="btn-modal btn-cancel" @click="showAccountModal=false">取消</button><button class="btn-modal btn-save" @click="submitAccount">确认</button></div>
      </div>
    </div>

    <div class="modal-overlay" v-if="showCategoryModal" @click.self="showCategoryModal = false">
      <div class="modal-card">
        <h3>{{ isCatEdit ? '🔧 编辑分类' : '➕ 新增分类' }}</h3>
        <div class="modal-form">
          <label>分类名称</label>
          <input v-model="categoryForm.name" placeholder="例如：早餐">
          
          <label style="margin-top: 10px;">父级分类 (可选)</label>
          <select v-model="categoryForm.parent_id">
            <option value="">无 (作为主分类)</option>
            <option v-for="p in parentCategoryOptions" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </div>
        <div class="modal-actions">
          <button class="btn-modal btn-cancel" @click="showCategoryModal=false">取消</button>
          <button class="btn-modal btn-save" @click="submitCategory">保存</button>
        </div>
      </div>
    </div>

  </div>
</template>

<style>
/* 保持原有样式，新增分类树相关样式 */
body { margin: 0; font-family: -apple-system, sans-serif; background-color: #f0f0f0; color: #333; }
.app-layout { display: flex; height: 100vh; width: 100vw; }
.sidebar { width: 240px; background: #f7f7f7; border-right: 1px solid #ddd; display: flex; flex-direction: column; }
.main-content { flex: 1; display: flex; flex-direction: column; background: #fff; overflow: hidden; }
.view-container { display: flex; flex-direction: column; height: 100%; }
.top-stats { height: 80px; padding: 0 30px; border-bottom: 1px solid #eee; display: flex; align-items: center; gap: 40px; background: #fafafa; }
.table-container { flex: 1; overflow-y: auto; padding: 20px; }
.settings-view { background: #f9f9f9; }
.settings-tabs { display: flex; padding: 20px 30px 0; gap: 10px; border-bottom: 1px solid #ddd; background: white; }
.settings-tabs button { padding: 10px 20px; background: none; border: none; border-bottom: 3px solid transparent; cursor: pointer; font-size: 15px; color: #666; }
.settings-tabs button.active { border-color: #3498db; color: #3498db; font-weight: bold; }
.settings-panel { padding: 30px; max-width: 800px; margin: 0 auto; width: 100%; box-sizing: border-box; }
.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.btn-sm { padding: 6px 12px; border-radius: 4px; border: none; cursor: pointer; font-size: 13px; margin-left: 5px; }
.btn-sm.primary { background: #3498db; color: white; }
.btn-sm.danger { background: #fff0f0; color: #e74c3c; } 
/* 通用弹窗按钮 */
.modal-actions { margin-top: 25px; padding-top: 20px; border-top: 1px solid #f0f0f0; display: flex; gap: 15px; justify-content: flex-end; }
.btn-modal { padding: 10px 24px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; border: none; transition: all 0.2s ease; outline: none; }
.btn-cancel { background-color: #f5f7fa; color: #666; } .btn-cancel:hover { background-color: #e4e7ed; color: #333; }
.btn-save { background: linear-gradient(135deg, #3498db, #2980b9); color: white; box-shadow: 0 4px 10px rgba(52, 152, 219, 0.3); } .btn-save:hover { transform: translateY(-2px); box-shadow: 0 6px 15px rgba(52, 152, 219, 0.4); } .btn-save:active { transform: translateY(0); }
/* 账户列表 */
.account-list { background: white; border: 1px solid #eee; border-radius: 8px; overflow: hidden; }
.account-row { display: flex; padding: 15px; border-bottom: 1px solid #eee; align-items: center; }
.account-row.header { background: #fafafa; font-weight: bold; color: #888; font-size: 13px; }
.badge { background: #eee; padding: 2px 8px; border-radius: 10px; font-size: 12px; color: #666; }
/* 分类树 */
.category-tree { display: flex; flex-direction: column; gap: 10px; }
.tree-node { background: white; border: 1px solid #eee; border-radius: 8px; overflow: hidden; }
.node-content { display: flex; justify-content: space-between; align-items: center; padding: 10px 15px; }
.node-content.parent { background: #fbfbfb; font-weight: 500; }
.node-content.parent.income { border-left: 4px solid #27ae60; }
.node-content.parent:not(.income) { border-left: 4px solid #c0392b; }
.node-content.child { border-top: 1px solid #f5f5f5; padding-left: 30px; font-size: 0.95em; color: #666; }
.node-actions { display: flex; gap: 10px; opacity: 0; transition: opacity 0.2s; }
.node-content:hover .node-actions { opacity: 1; }
.btn-text { background: none; border: none; color: #3498db; cursor: pointer; font-size: 12px; padding: 0; }
.btn-text:hover { text-decoration: underline; }
.btn-text.danger { color: #e74c3c; }
/* 模态框通用 */
.modal-overlay { position: fixed; top:0; left:0; width:100%; height:100%; background: rgba(0,0,0,0.4); display: flex; justify-content: center; align-items: center; z-index: 999; }
.modal-card { background: white; padding: 25px; border-radius: 10px; width: 400px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); }
.modal-form label { font-size: 0.9em; font-weight: bold; color: #555; margin-bottom: 3px; display: block; margin-top: 10px; }
.modal-form input, .modal-form select { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }
.type-tabs { display: flex; border: 1px solid #3498db; border-radius: 6px; overflow: hidden; margin-bottom: 20px; }
.type-tabs label { flex: 1; text-align: center; padding: 8px; cursor: pointer; color: #3498db; }
.type-tabs label.active { background: #3498db; color: white; }
.modal-form .row { display: flex; gap: 10px; margin-top: 0; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; padding: 10px; border-bottom: 1px solid #eee; color: #888; }
td { padding: 12px 10px; border-bottom: 1px solid #f5f5f5; }
.btn-icon { border: none; background: none; opacity: 0.3; cursor: pointer; } .btn-icon:hover { opacity: 1; color: red; }
.nav-item { padding: 10px 20px; cursor: pointer; display: flex; align-items: center; gap: 10px; color: #555; } .nav-item:hover { background: #eaeaea; } .nav-item.active { background: #e0e0e0; color: #000; font-weight: 500; border-left: 3px solid #3498db; }
.nav-item.sub-item { padding-left: 45px; font-size: 13px; justify-content: space-between; }
.logo-area { padding: 20px; display: flex; align-items: center; gap: 10px; }
.group-header { padding: 5px 20px; font-size: 12px; color: #999; display: flex; justify-content: space-between; margin-top: 10px; }
.text-right { text-align: right; } .text-red { color: #e74c3c; } .text-green { color: #27ae60; } .text-blue { color: #3498db; } .text-gray { color: #999; }
.spacer { flex: 1; }
</style>
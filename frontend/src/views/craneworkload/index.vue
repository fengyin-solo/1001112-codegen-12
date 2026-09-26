<template>
  <section class="page" data-module="crane-workload">
    <header class="page-head">
      <div>
        <h2>岸桥作业量统计</h2>
        <p class="page-desc">按设备编号与班次汇总岸桥作业量、司机与作业区域，并生成班次作业量视图；数字实时与设备台账核对。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" :disabled="loading" @click="reload">
          {{ loading ? '正在取数…' : '刷新数据' }}
        </button>
      </div>
    </header>

    <div v-if="errorMessage" class="error-banner">
      <span class="error-text">{{ errorMessage }}</span>
      <button class="btn" type="button" :disabled="loading" @click="reload">重试</button>
    </div>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <p class="consistency" :class="consistent ? '' : 'warn-text'">
      {{ consistencyText }}
    </p>

    <h3 class="section-title">班次作业量视图</h3>
    <table class="data-table">
      <thead>
        <tr>
          <th>班次</th>
          <th>作业量合计（TEU）</th>
          <th>记录条数</th>
          <th>待核实</th>
          <th>设备状态分布</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in shiftView" :key="row.班次">
          <td>{{ row.班次 }}</td>
          <td>{{ row.作业量合计 }}</td>
          <td>{{ row.记录条数 }}</td>
          <td>{{ row.待核实条数 }}</td>
          <td>{{ statusDistText(row.设备状态分布) }}</td>
        </tr>
        <tr v-if="!shiftView.length">
          <td colspan="5" class="empty-state">暂无班次作业量数据</td>
        </tr>
      </tbody>
    </table>

    <h3 class="section-title">待核实记录（作业量为空或设备编号挂不上台账）</h3>
    <table class="data-table">
      <thead>
        <tr>
          <th>设备编号</th>
          <th>班次</th>
          <th>司机姓名</th>
          <th>作业区域</th>
          <th>作业量（TEU）</th>
          <th>问题说明</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in flagged" :key="String(row.id)" class="row-flagged">
          <td>{{ row.设备编号 }}</td>
          <td>{{ row.班次 }}</td>
          <td>{{ row.司机姓名 }}</td>
          <td>{{ row.作业区域 }}</td>
          <td>{{ row.作业量 ?? '—' }}</td>
          <td class="warn-text">{{ row.issues.join('；') }}</td>
        </tr>
        <tr v-if="!flagged.length">
          <td colspan="6" class="empty-state">没有待核实记录，全部已对上台账</td>
        </tr>
      </tbody>
    </table>

    <h3 class="section-title">作业记录明细</h3>
    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>设备编号</span>
        <input v-model="filters.keyword" placeholder="按设备编号检索" />
      </label>
      <label class="filter-item">
        <span>班次</span>
        <select v-model="filters.shift">
          <option value="">全部班次</option>
          <option v-for="name in shifts" :key="name" :value="name">{{ name }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th>设备编号</th>
          <th>班次</th>
          <th>司机姓名</th>
          <th>作业区域</th>
          <th>作业量（TEU）</th>
          <th>设备状态</th>
          <th>核对结果</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in records" :key="String(row.id)" :class="{ 'row-flagged': row.issues.length }">
          <td>{{ row.设备编号 }}</td>
          <td>{{ row.班次 }}</td>
          <td>{{ row.司机姓名 }}</td>
          <td>{{ row.作业区域 }}</td>
          <td>{{ row.作业量 ?? '—' }}</td>
          <td>{{ row.设备状态 }}</td>
          <td :class="{ 'warn-text': row.issues.length }">
            {{ row.issues.length ? row.issues.join('；') : '正常' }}
          </td>
        </tr>
        <tr v-if="!records.length">
          <td colspan="7" class="empty-state">当前条件下没有作业记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ records.length }} 条作业记录</span>
      <span v-if="ledgerTotal !== null">设备清单共 {{ ledgerTotal }} 台</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type WorkloadRecord = {
  id: number | string
  设备编号: string
  班次: string
  司机姓名: string
  作业区域: string
  作业量: number | null
  设备状态: string
  issues: string[]
}

type ShiftRow = {
  班次: string
  作业量合计: number
  记录条数: number
  待核实条数: number
  设备状态分布: Record<string, number>
}

type WorkloadView = {
  summary: { 台账设备数: number; 作业记录数: number; 作业量总计: number; 待核实记录: number }
  shift_view: ShiftRow[]
  records: WorkloadRecord[]
  flagged: WorkloadRecord[]
  shifts: string[]
}

const ENDPOINT = '/api/crane'

const summary = ref<WorkloadView['summary']>({ 台账设备数: 0, 作业记录数: 0, 作业量总计: 0, 待核实记录: 0 })
const shiftView = ref<ShiftRow[]>([])
const records = ref<WorkloadRecord[]>([])
const flagged = ref<WorkloadRecord[]>([])
const shifts = ref<string[]>([])
const ledgerTotal = ref<number | null>(null)
const loading = ref(false)
const errorMessage = ref('')
const filters = ref({ keyword: '', shift: '' })

const statCards = computed(() => [
  { label: '台账设备数', value: summary.value.台账设备数 },
  { label: '作业记录数', value: summary.value.作业记录数 },
  { label: '作业量总计（TEU）', value: summary.value.作业量总计 },
  { label: '待核实记录', value: summary.value.待核实记录 },
])

const consistent = computed(() => ledgerTotal.value !== null && ledgerTotal.value === summary.value.台账设备数)

const consistencyText = computed(() => {
  if (ledgerTotal.value === null) {
    return '设备清单数量未取到，无法核对'
  }
  return consistent.value
    ? `已核对：统计口径覆盖台账设备 ${summary.value.台账设备数} 台，与设备清单一致`
    : `统计口径（${summary.value.台账设备数} 台）与设备清单（${ledgerTotal.value} 台）不一致，请刷新重试`
})

function statusDistText(dist: Record<string, number>): string {
  const parts = Object.entries(dist).map(([status, count]) => `${status}×${count}`)
  return parts.length ? parts.join(' · ') : '—'
}

function resetFilters() {
  filters.value = { keyword: '', shift: '' }
  void reload()
}

async function readDetail(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string }
    if (body.detail) {
      return body.detail
    }
  } catch {
    // 响应不是 JSON 时退回默认说明
  }
  return `${fallback}（接口返回 ${response.status}）`
}

async function reload() {
  loading.value = true
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.value.keyword) {
    query.set('keyword', filters.value.keyword)
  }
  if (filters.value.shift) {
    query.set('shift', filters.value.shift)
  }
  try {
    const [statsResp, ledgerResp] = await Promise.all([
      request(`${ENDPOINT}/workload?${query.toString()}`),
      // 设备清单单独取一次总数，用来核对统计口径是否与台账一致
      request(`${ENDPOINT}?page=1&size=1`),
    ])
    if (!statsResp.ok) {
      throw new Error(await readDetail(statsResp, '作业量统计取数失败，请稍后重试'))
    }
    if (!ledgerResp.ok) {
      throw new Error(await readDetail(ledgerResp, '设备清单读取失败，请稍后重试'))
    }
    const payload = (await statsResp.json()) as WorkloadView
    const ledger = (await ledgerResp.json()) as { total?: number }
    summary.value = payload.summary
    shiftView.value = payload.shift_view ?? []
    records.value = payload.records ?? []
    flagged.value = payload.flagged ?? []
    shifts.value = payload.shifts ?? []
    ledgerTotal.value = ledger.total ?? null
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '岸桥作业量统计读取失败，请重试'
  } finally {
    loading.value = false
  }
}

onMounted(reload)
</script>

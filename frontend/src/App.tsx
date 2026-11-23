import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'

const projectId = 'demo-project'
const budgetsUrl = '/api/projects/' + projectId + '/budgets'

type Category = { id: string; name: string }
type AnnualPlan = {
  categories: Category[]
  planned_cents: Record<string, number>
  planned_total_cents: number
}
const euros = new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' })

function toInput(cents: number): string {
  return (cents / 100).toFixed(2).replace('.', ',')
}

function toCents(value: string): number {
  const amount = value.trim()
  if (!/^\d{1,10}(?:[,.]\d{1,2})?$/.test(amount)) {
    throw new Error('Bitte gib einen Betrag zwischen 0 und 9.999.999.999,99 € mit höchstens zwei Nachkommastellen ein.')
  }

  const [whole, cents = ''] = amount.split(/[,.]/)
  return Number(whole) * 100 + Number(cents.padEnd(2, '0'))
}

async function getJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options)
  if (!response.ok) {
    throw new Error('Die Anfrage ist fehlgeschlagen. Bitte versuche es erneut.')
  }
  return response.json()
}

function writeJson<T>(url: string, method: 'PUT' | 'POST' | 'PATCH', data: unknown) {
  return getJson<T>(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

function PlanEditor({ year, onSaving }: { year: number; onSaving: (saving: boolean) => void }) {
  const endpoint = budgetsUrl + '/' + year
  const categoriesUrl = budgetsUrl + '/categories'
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [plan, setPlan] = useState<AnnualPlan>()
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [loadError, setLoadError] = useState(false)
  const [attempt, setAttempt] = useState(0)

  function applySavedPlan(data: AnnualPlan) {
    setPlan(data)
    setDraft(Object.fromEntries(Object.entries(data.planned_cents).map(([id, cents]) => [id, toInput(cents)])))
  }

  useEffect(() => {
    const controller = new AbortController()
    getJson<AnnualPlan>(endpoint, { signal: controller.signal }).then((data) => {
      if (!controller.signal.aborted) applySavedPlan(data)
    }).catch(() => {
      if (!controller.signal.aborted) setLoadError(true)
    })
    return () => controller.abort()
  }, [endpoint, attempt])

  async function save(action: () => Promise<void>, success: string) {
    if (saving) return
    setSaving(true)
    onSaving(true)
    setError('')
    setNotice('')
    try {
      await action()
      setNotice(success)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Das Speichern ist fehlgeschlagen.')
    } finally {
      setSaving(false)
      onSaving(false)
    }
  }

  function submitPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void save(async () => {
      const costs = Object.fromEntries(Object.entries(draft).map(([id, value]) => [id, toCents(value)]))
      applySavedPlan(await writeJson<AnnualPlan>(endpoint, 'PUT', costs))
    }, 'Sollkosten gespeichert.')
  }

  function addCategory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const name = new FormData(form).get('name')
    void save(async () => {
      const category = await writeJson<Category>(categoriesUrl, 'POST', { name })
      setPlan((previous) => previous && { ...previous, categories: [...previous.categories, category] })
      setDraft((previous) => ({ ...previous, [category.id]: toInput(0) }))
      form.reset()
    }, 'Kostenart hinzugefügt.')
  }

  function renameCategory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const fields = new FormData(form)
    const id = String(fields.get('category'))
    if (!id) return
    void save(async () => {
      const category = await writeJson<Category>(categoriesUrl + '/' + id, 'PATCH', { name: fields.get('name') })
      setPlan((previous) => previous && {
        ...previous, categories: previous.categories.map((item) => item.id === id ? category : item),
      })
      form.reset()
    }, 'Kostenart umbenannt.')
  }

  if (!plan) {
    return loadError ? (
      <div className="feedback">
        <p role="alert">Die Sollkosten konnten nicht geladen werden.</p>
        <button type="button" onClick={() => { setLoadError(false); setAttempt(attempt + 1) }}>
          Erneut laden
        </button>
      </div>
    ) : <p role="status">Sollkosten werden geladen …</p>
  }

  return (
    <div className="plan-editor">
      <form onSubmit={submitPlan}>
        <table>
          <thead>
            <tr><th scope="col">Kostenart</th><th scope="col">Sollbetrag (EUR)</th></tr>
          </thead>
          <tbody>
            {plan.categories.map(({ id, name }) => (
              <tr key={id}>
                <th scope="row"><label htmlFor={'cost-' + id}>{name}</label></th>
                <td>
                  <input id={'cost-' + id} value={draft[id]} inputMode="decimal" required disabled={saving}
                    onChange={(event) => setDraft({ ...draft, [id]: event.target.value })} />
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr><th scope="row">Gespeichertes Soll</th><td>{euros.format(plan.planned_total_cents / 100)}</td></tr>
          </tfoot>
        </table>
        <div className="budget-fields">
          <button type="submit" disabled={saving}>Sollkosten speichern</button>
        </div>
      </form>
      <details>
        <summary>Kostenarten verwalten</summary>
        <form className="budget-fields" onSubmit={addCategory}>
          <label htmlFor="new-category">Neue Kostenart</label>
          <input id="new-category" name="name" maxLength={120} required disabled={saving} />
          <button type="submit" disabled={saving}>Hinzufügen</button>
        </form>
        {plan.categories.length > 0 && (
          <form className="budget-fields" onSubmit={renameCategory}>
            <label htmlFor="rename-category">Kostenart</label>
            <select id="rename-category" name="category" required disabled={saving} defaultValue="">
              <option value="" disabled>Auswählen</option>
              {plan.categories.map(({ id, name }) => <option key={id} value={id}>{name}</option>)}
            </select>
            <label htmlFor="category-name">Neuer Name</label>
            <input id="category-name" name="name" maxLength={120} required disabled={saving} />
            <button type="submit" disabled={saving}>Umbenennen</button>
          </form>
        )}
      </details>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
    </div>
  )
}

function App() {
  const currentYear = new Date().getFullYear()
  const [year, setYear] = useState(currentYear)
  const [yearInput, setYearInput] = useState(String(currentYear))
  const [saving, setSaving] = useState(false)

  function selectYear(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setYear(Number(yearInput))
  }

  return (
    <main className="budget-page">
      <header>
        <p>Demo-Projekt</p>
        <h1>Sollkostenplanung</h1>
      </header>
      <section className="budget-card" aria-labelledby="plan-heading">
        <div className="budget-toolbar">
          <h2 id="plan-heading">Jahresplan {year}</h2>
          <form className="year-picker" onSubmit={selectYear}>
            <label htmlFor="year">Haushaltsjahr</label>
            <input id="year" type="number" min={2000} max={2100} required value={yearInput}
              disabled={saving} onChange={(event) => setYearInput(event.target.value)} />
            <button type="submit" disabled={saving}>Anzeigen</button>
          </form>
        </div>
        <PlanEditor key={year} year={year} onSaving={setSaving} />
      </section>
    </main>
  )
}

export default App

import { describe, expect, it } from 'vitest'
import { changeMode, resolvePeriod, shiftPeriod } from './periods'

describe('periodi', () => {
  it('il mese copre dal primo all ultimo giorno', () => {
    const r = resolvePeriod({ mode: 'month', anchor: '2026-02-14' })
    expect(r.from).toBe('2026-02-01')
    expect(r.to).toBe('2026-02-28')
    expect(r.navigable).toBe(true)
  })

  it('la settimana va da lunedi a domenica', () => {
    // il 20 settembre 2026 è una domenica
    const r = resolvePeriod({ mode: 'week', anchor: '2026-09-20' })
    expect(r.from).toBe('2026-09-14')
    expect(r.to).toBe('2026-09-20')
  })

  it('indietro di un mese dal 31 non salta a marzo', () => {
    // il bug classico: 31 gennaio meno un mese darebbe il 31 febbraio, cioè marzo
    const p = shiftPeriod({ mode: 'month', anchor: '2026-03-31' }, -1)
    expect(resolvePeriod(p).from).toBe('2026-02-01')
    expect(resolvePeriod(p).to).toBe('2026-02-28')
  })

  it('avanti e indietro riporta allo stesso intervallo', () => {
    for (const mode of ['month', 'week', 'year'] as const) {
      const p = { mode, anchor: '2026-05-17' }
      const andata = resolvePeriod(shiftPeriod(shiftPeriod(p, 1), -1))
      const fermo = resolvePeriod(p)
      expect(andata).toEqual(fermo)
    }
  })

  it('le finestre mobili non sono navigabili e coprono il numero giusto di giorni', () => {
    for (const [mode, giorni] of [['last7', 7], ['last30', 30], ['last365', 365]] as const) {
      const r = resolvePeriod({ mode, anchor: '2026-09-20' })
      expect(r.navigable).toBe(false)
      const span = (new Date(r.to).getTime() - new Date(r.from).getTime()) / 86400000
      expect(span + 1).toBe(giorni)
    }
  })

  it('le finestre mobili ignorano lo spostamento', () => {
    const p = { mode: 'last30' as const, anchor: '2026-09-20' }
    expect(shiftPeriod(p, -3)).toEqual(p)
  })

  it('cambiare modalita riporta l ancora a oggi', () => {
    const oggi = new Date()
    const p = changeMode('year')
    expect(p.anchor.slice(0, 4)).toBe(String(oggi.getFullYear()))
  })
})

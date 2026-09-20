import { describe, expect, it } from 'vitest'
import { parseAmount } from './format'

describe('parseAmount', () => {
  it('toglie il separatore delle migliaia e converte la virgola', () => {
    expect(parseAmount('1.250,80')).toBe('1250.80')
    expect(parseAmount('1.250.800,50')).toBe('1250800.50')
    expect(parseAmount('1 250,80')).toBe('1250.80')
  })

  it('lascia intatto il punto decimale', () => {
    expect(parseAmount('45.30')).toBe('45.30')
    expect(parseAmount('0.5')).toBe('0.5')
  })

  it('accetta la sola virgola', () => {
    expect(parseAmount('250,50')).toBe('250.50')
    expect(parseAmount('  12,00  ')).toBe('12.00')
  })

  it('accetta un intero senza separatori', () => {
    expect(parseAmount('2000')).toBe('2000')
  })

  it('legge un punto seguito da tre cifre come migliaia, secondo la convenzione italiana', () => {
    expect(parseAmount('1.250')).toBe('1250')
  })
})

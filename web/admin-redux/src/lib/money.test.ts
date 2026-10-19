import { describe, expect, it } from 'vitest'
import { formatKopecks } from './money'
import { plain } from '../test/text'


describe('formatKopecks', () => {
  it('целые рубли без копеек', () => {
    expect(plain(formatKopecks(3550000))).toBe('35 500 ₽')
    expect(plain(formatKopecks(0))).toBe('0 ₽')
  })

  it('копейки двумя знаками', () => {
    expect(plain(formatKopecks(12345))).toBe('123,45 ₽')
    expect(plain(formatKopecks(105))).toBe('1,05 ₽')
    expect(plain(formatKopecks(1))).toBe('0,01 ₽')
  })

  it('большие суммы без потери точности', () => {
    expect(plain(formatKopecks(123456789012))).toBe('1 234 567 890,12 ₽')
  })

  it('отрицательные', () => {
    expect(plain(formatKopecks(-2550))).toBe('−25,50 ₽')
  })

  it('не принимает дробные копейки', () => {
    expect(() => formatKopecks(10.5)).toThrow(TypeError)
  })
})

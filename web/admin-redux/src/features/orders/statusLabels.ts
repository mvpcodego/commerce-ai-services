import type { OrderStatus } from '../../api/types'

export const STATUS_LABEL: Record<OrderStatus, string> = {
  new: 'Новый',
  confirmed: 'Подтверждён',
  shipped: 'Отправлен',
  delivered: 'Доставлен',
  cancelled: 'Отменён',
}

/** Подпись кнопки «перевести в статус». */
export const TRANSITION_ACTION: Record<OrderStatus, string> = {
  new: 'Вернуть в новые',
  confirmed: 'Подтвердить',
  shipped: 'Отгрузить',
  delivered: 'Отметить доставленным',
  cancelled: 'Отменить заказ',
}

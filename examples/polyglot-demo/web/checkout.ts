import { calculateTotal } from './pricing';

export function checkout(price: number, quantity: number): number {
  return calculateTotal(price, quantity);
}

export class CheckoutView {
  render(): string {
    return 'Review your order';
  }
}

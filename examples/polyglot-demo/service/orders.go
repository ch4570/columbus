package orders

type Order struct {
    Quantity int
}

func ValidateOrder(order Order) bool {
    return order.Quantity > 0
}

func SubmitOrder(order Order) bool {
    return ValidateOrder(order)
}

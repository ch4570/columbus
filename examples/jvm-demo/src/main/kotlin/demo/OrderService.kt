package demo

class OrderService(private val gateway: PaymentGateway) {
    fun cancel(orderId: String): String {
        return gateway.refund(orderId)
    }
}

fun cancelOrder(service: OrderService, orderId: String): String {
    return service.cancel(orderId)
}

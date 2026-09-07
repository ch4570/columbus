package demo;

public class PaymentGateway {
    public String refund(String orderId) {
        return "refunded:" + orderId;
    }
}

#include "totals.h"

int calculate_total(int price, int quantity) {
    return price * quantity;
}

int demo_total() {
    return calculate_total(25, 2);
}

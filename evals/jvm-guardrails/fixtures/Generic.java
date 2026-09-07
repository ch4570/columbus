class T { void hit() {} }
interface API { void hit(); }
class Generic<T extends API> {
    void run(T item) { item.hit(); }
}

class Base { void hit(int n) {} }
class Inherited extends Base {
    void hit(String s) {}
    void run() { hit(1); }
}

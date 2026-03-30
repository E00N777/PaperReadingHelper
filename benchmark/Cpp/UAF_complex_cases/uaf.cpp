/**
 * ============================================================================
 *  UAF (Use-After-Free) Vulnerability Test Suite for AI-Driven SAST
 * ============================================================================
 *
 *  This file contains intentionally planted UAF vulnerabilities at three
 *  difficulty levels:
 *    - SIMPLE   (S-xx): Direct free-then-use, obvious patterns
 *    - MEDIUM   (M-xx): Cross-function, conditional, container-related
 *    - COMPLEX  (C-xx): Multi-threaded, callback, polymorphic, temporal
 *
 *  Compile: g++ -std=c++17 -pthread -o uaf_test uaf_test_suite.cpp
 *  Run:     ./uaf_test
 *
 *  WARNING: This code is intentionally vulnerable. Do NOT use in production.
 * ============================================================================
 */

 #include <iostream>
 #include <string>
 #include <vector>
 #include <map>
 #include <unordered_map>
 #include <memory>
 #include <functional>
 #include <thread>
 #include <mutex>
 #include <condition_variable>
 #include <atomic>
 #include <algorithm>
 #include <cstring>
 #include <cstdlib>
 #include <cassert>
 #include <queue>
 #include <set>
 #include <optional>
 #include <variant>
 #include <chrono>
 #include <sstream>
 #include <numeric>
 #include <stack>
 
 // ============================================================================
 //  Forward declarations and utility types
 // ============================================================================
 
 static int g_test_counter = 0;
 static int g_vuln_triggered = 0;
 
 #define TEST_HEADER(id, level, desc) \
     do { \
         g_test_counter++; \
         std::cout << "\n[" << id << "] (" << level << ") " << desc << std::endl; \
     } while(0)
 
 #define SAFE_GUARD(ptr) \
     do { \
         if (!(ptr)) { std::cout << "  [guard] null pointer detected" << std::endl; return; } \
     } while(0)
 
 // Dummy sink to prevent compiler from optimizing away reads
 volatile int g_sink = 0;
 
 void consume(int val) {
     g_sink = val;
 }
 
 void consume_ptr(void* p) {
     if (p) g_sink = *reinterpret_cast<int*>(p);
 }
 
 // ============================================================================
 //  SECTION 1: SIMPLE UAF VULNERABILITIES (S-01 to S-05)
 // ============================================================================
 
 // ---------------------------------------------------------------------------
 // S-01: Direct delete then dereference
 // ---------------------------------------------------------------------------
 void vuln_s01_direct_delete_deref() {
     TEST_HEADER("S-01", "SIMPLE", "Direct delete then dereference");
 
     int* p = new int(42);
     std::cout << "  Before delete: " << *p << std::endl;
     delete p;
     // UAF: p is dangling, reading from freed memory
     std::cout << "  After delete (UAF): " << *p << std::endl;  // [S-01] UAF HERE
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // S-02: Free then write
 // ---------------------------------------------------------------------------
 void vuln_s02_free_then_write() {
     TEST_HEADER("S-02", "SIMPLE", "Free then write to freed memory");
 
     char* buf = (char*)malloc(64);
     strcpy(buf, "hello world");
     std::cout << "  Before free: " << buf << std::endl;
     free(buf);
     // UAF: writing to freed memory
     strcpy(buf, "use after free");  // [S-02] UAF HERE
     std::cout << "  After free (UAF): " << buf << std::endl;
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // S-03: Array delete then access
 // ---------------------------------------------------------------------------
 void vuln_s03_array_delete_access() {
     TEST_HEADER("S-03", "SIMPLE", "Array delete[] then element access");
 
     int* arr = new int[10];
     for (int i = 0; i < 10; i++) arr[i] = i * 10;
     std::cout << "  Before delete: arr[5] = " << arr[5] << std::endl;
     delete[] arr;
     // UAF: accessing element of deleted array
     int val = arr[5];  // [S-03] UAF HERE
     consume(val);
     std::cout << "  After delete (UAF): arr[5] = " << val << std::endl;
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // S-04: Double free (variant of UAF)
 // ---------------------------------------------------------------------------
 void vuln_s04_double_free() {
     TEST_HEADER("S-04", "SIMPLE", "Double free");
 
     int* p = new int(99);
     delete p;
     // UAF/Double-free: freeing already freed memory
     delete p;  // [S-04] DOUBLE FREE HERE
     std::cout << "  Double free executed" << std::endl;
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // S-05: Struct member access after delete
 // ---------------------------------------------------------------------------
 struct SimpleNode {
     int value;
     char name[32];
     double weight;
 };
 
 void vuln_s05_struct_member_after_delete() {
     TEST_HEADER("S-05", "SIMPLE", "Struct member access after delete");
 
     SimpleNode* node = new SimpleNode{42, "test_node", 3.14};
     std::cout << "  Before delete: " << node->name << " = " << node->value << std::endl;
     delete node;
     // UAF: accessing struct members after deletion
     int v = node->value;        // [S-05] UAF HERE
     double w = node->weight;    // [S-05] UAF HERE (secondary)
     consume(v);
     std::cout << "  After delete (UAF): value=" << v << " weight=" << w << std::endl;
     g_vuln_triggered++;
 }
 
 
 // ============================================================================
 //  SECTION 2: MEDIUM UAF VULNERABILITIES (M-01 to M-15)
 // ============================================================================
 
 // ---------------------------------------------------------------------------
 // M-01: UAF via returned pointer from function that deletes internally
 // ---------------------------------------------------------------------------
 struct Resource {
     int id;
     char data[128];
 };
 
 Resource* create_and_destroy_resource() {
     Resource* r = new Resource{1, "important data"};
     // Simulating some processing then cleanup
     Resource* alias = r;
     delete r;       // deleted here
     return alias;   // returning dangling pointer
 }
 
 void vuln_m01_returned_dangling_ptr() {
     TEST_HEADER("M-01", "MEDIUM", "Returned dangling pointer from function");
 
     Resource* res = create_and_destroy_resource();
     // UAF: using pointer that was freed inside the called function
     std::cout << "  Resource id (UAF): " << res->id << std::endl;  // [M-01] UAF HERE
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // M-02: Conditional path UAF — only one branch frees
 // ---------------------------------------------------------------------------
 void vuln_m02_conditional_uaf(bool flag) {
     TEST_HEADER("M-02", "MEDIUM", "Conditional path UAF");
 
     int* data = new int(100);
 
     if (flag) {
         std::cout << "  Flag is true, deleting..." << std::endl;
         delete data;
     } else {
         std::cout << "  Flag is false, keeping..." << std::endl;
     }
 
     // UAF: when flag==true, data is freed but still used
     std::cout << "  Value (UAF if flag=true): " << *data << std::endl;  // [M-02] UAF HERE
     if (!flag) delete data;  // cleanup for non-UAF path
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // M-03: UAF through vector invalidation (iterator invalidation)
 // ---------------------------------------------------------------------------
 void vuln_m03_vector_iterator_invalidation() {
     TEST_HEADER("M-03", "MEDIUM", "Vector iterator invalidation UAF");
 
     std::vector<int> vec = {1, 2, 3, 4, 5};
     int* elem_ptr = &vec[2];  // pointer to element
 
     std::cout << "  Before realloc: *elem_ptr = " << *elem_ptr << std::endl;
 
     // Force reallocation by adding many elements
     for (int i = 0; i < 1000; i++) {
         vec.push_back(i);
     }
 
     // UAF: elem_ptr now points to freed memory after reallocation
     std::cout << "  After realloc (UAF): *elem_ptr = " << *elem_ptr << std::endl;  // [M-03] UAF HERE
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // M-04: UAF through string internal buffer (SSO boundary)
 // ---------------------------------------------------------------------------
 void vuln_m04_string_internal_buffer() {
     TEST_HEADER("M-04", "MEDIUM", "String internal buffer UAF after move");
 
     std::string s1 = "This is a long string that exceeds SSO buffer size and goes on heap for sure";
     const char* internal_ptr = s1.c_str();
 
     std::cout << "  Before move: " << internal_ptr << std::endl;
 
     std::string s2 = std::move(s1);  // s1's buffer is now owned by s2
 
     // UAF: internal_ptr may point to memory managed by s2 or invalidated
     // Accessing s1's old data through saved pointer
     std::cout << "  After move (potential UAF): " << internal_ptr << std::endl;  // [M-04] UAF HERE
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // M-05: UAF via map erase while holding pointer to value
 // ---------------------------------------------------------------------------
 void vuln_m05_map_erase_dangling() {
     TEST_HEADER("M-05", "MEDIUM", "Map erase with dangling pointer to value");
 
     std::map<std::string, std::string> config;
     config["database"] = "postgresql://localhost:5432/mydb";
     config["api_key"]  = "sk-secret-key-12345";
     config["timeout"]  = "30s";
 
     const std::string* db_ptr = &config["database"];
     std::cout << "  Before erase: " << *db_ptr << std::endl;
 
     config.erase("database");
 
     // UAF: db_ptr points to erased map entry
     std::cout << "  After erase (UAF): " << *db_ptr << std::endl;  // [M-05] UAF HERE
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // M-06: UAF through shared_ptr / raw pointer mix
 // ---------------------------------------------------------------------------
 void vuln_m06_shared_raw_mix() {
     TEST_HEADER("M-06", "MEDIUM", "shared_ptr / raw pointer mix UAF");
 
     int* raw = nullptr;
     {
         auto sp = std::make_shared<int>(777);
         raw = sp.get();  // raw pointer to shared_ptr's managed object
         std::cout << "  Inside scope: " << *raw << std::endl;
     }
     // shared_ptr destroyed, raw is dangling
 
     // UAF: raw points to freed memory
     std::cout << "  Outside scope (UAF): " << *raw << std::endl;  // [M-06] UAF HERE
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // M-07: UAF through unique_ptr reset
 // ---------------------------------------------------------------------------
 void vuln_m07_unique_ptr_reset() {
     TEST_HEADER("M-07", "MEDIUM", "unique_ptr reset with cached raw pointer");
 
     auto up = std::make_unique<int>(555);
     int* cached = up.get();
 
     std::cout << "  Before reset: " << *cached << std::endl;
     up.reset(new int(666));  // old object is deleted
 
     // UAF: cached points to the old deleted object
     std::cout << "  After reset (UAF): " << *cached << std::endl;  // [M-07] UAF HERE
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // M-08: UAF through swap + dangling reference
 // ---------------------------------------------------------------------------
 struct Buffer {
     char* data;
     size_t size;
 
     Buffer(size_t sz) : size(sz) { data = new char[sz]; memset(data, 'A', sz); }
     ~Buffer() { delete[] data; }
     Buffer(Buffer&& o) noexcept : data(o.data), size(o.size) { o.data = nullptr; o.size = 0; }
     Buffer& operator=(Buffer&& o) noexcept {
         delete[] data;
         data = o.data; size = o.size;
         o.data = nullptr; o.size = 0;
         return *this;
     }
     Buffer(const Buffer&) = delete;
     Buffer& operator=(const Buffer&) = delete;
 };
 
 void vuln_m08_swap_dangling() {
     TEST_HEADER("M-08", "MEDIUM", "Swap causes dangling reference UAF");
 
     std::vector<Buffer> buffers;
     buffers.emplace_back(64);
     buffers.emplace_back(128);
 
     char* ptr_to_first = buffers[0].data;
     std::cout << "  Before swap: ptr_to_first[0] = " << ptr_to_first[0] << std::endl;
 
     // Swap causes internal data pointers to change
     std::swap(buffers[0], buffers[1]);
 
     // ptr_to_first now points to data owned by buffers[1] (swapped)
     // If buffers[1] is destroyed, ptr_to_first becomes dangling
     buffers.pop_back();  // destroys what was buffers[0] originally
 
     // UAF: ptr_to_first points to freed data
     std::cout << "  After swap+pop (UAF): " << ptr_to_first[0] << std::endl;  // [M-08] UAF HERE
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // M-09: UAF in exception handling path
 // ---------------------------------------------------------------------------
 void vuln_m09_exception_path_uaf() {
     TEST_HEADER("M-09", "MEDIUM", "UAF in exception handling path");
 
     int* data = new int(12345);
 
     try {
         std::cout << "  Before exception: " << *data << std::endl;
         delete data;
         // Simulate an operation that might throw
         throw std::runtime_error("simulated error");
     } catch (const std::exception& e) {
         std::cout << "  Caught: " << e.what() << std::endl;
         // UAF: data was deleted before the throw
         std::cout << "  In catch (UAF): " << *data << std::endl;  // [M-09] UAF HERE
     }
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // M-10: UAF through aliased pointers in loop
 // ---------------------------------------------------------------------------
 void vuln_m10_aliased_loop_uaf() {
     TEST_HEADER("M-10", "MEDIUM", "Aliased pointer UAF in loop");
 
     int* ptrs[5];
     for (int i = 0; i < 5; i++) {
         ptrs[i] = new int(i * 100);
     }
 
     // Create alias
     int* alias = ptrs[2];
 
     // Delete all in loop
     for (int i = 0; i < 5; i++) {
         delete ptrs[i];
     }
 
     // UAF: alias still references deleted ptrs[2]
     std::cout << "  Alias after loop delete (UAF): " << *alias << std::endl;  // [M-10] UAF HERE
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // M-11: UAF via lambda capture by reference
 // ---------------------------------------------------------------------------
 std::function<int()> create_dangling_lambda() {
     int* heap_val = new int(9999);
     auto lambda = [&heap_val]() -> int {
         return *heap_val;  // captures reference to local pointer
     };
     delete heap_val;
     return lambda;  // lambda now has dangling reference
 }
 
 void vuln_m11_lambda_capture_uaf() {
     TEST_HEADER("M-11", "MEDIUM", "Lambda capture by reference UAF");
 
     auto fn = create_dangling_lambda();
     // UAF: lambda's captured reference to heap_val is dangling
     // Note: this is actually UB because heap_val itself (the local variable) is gone
     // For the purpose of SAST testing, the delete before return is the key pattern
     std::cout << "  Lambda result (UAF): " << fn() << std::endl;  // [M-11] UAF HERE
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // M-12: UAF through placement new misuse
 // ---------------------------------------------------------------------------
 struct Gadget {
     int serial;
     char model[32];
     void describe() {
         std::cout << "  Gadget #" << serial << " model: " << model << std::endl;
     }
 };
 
 void vuln_m12_placement_new_uaf() {
     TEST_HEADER("M-12", "MEDIUM", "Placement new with premature buffer free");
 
     char* buffer = new char[sizeof(Gadget)];
     Gadget* g = new (buffer) Gadget{42, "ProMax"};
 
     g->describe();
 
     delete[] buffer;  // free the underlying buffer
 
     // UAF: Gadget object sits in freed memory
     g->describe();  // [M-12] UAF HERE
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // M-13: UAF through deque shrink
 // ---------------------------------------------------------------------------
 void vuln_m13_deque_invalidation() {
     TEST_HEADER("M-13", "MEDIUM", "Deque invalidation UAF");
 
     std::deque<int> dq;
     for (int i = 0; i < 100; i++) dq.push_back(i);
 
     int* mid_ptr = &dq[50];
     std::cout << "  Before shrink: *mid_ptr = " << *mid_ptr << std::endl;
 
     // Erase elements from front — may invalidate pointers
     dq.erase(dq.begin(), dq.begin() + 60);
 
     // UAF: mid_ptr likely invalidated by erasure
     std::cout << "  After erase (UAF): *mid_ptr = " << *mid_ptr << std::endl;  // [M-13] UAF HERE
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // M-14: UAF through std::any / type-erased container
 // ---------------------------------------------------------------------------
 void vuln_m14_any_type_erasure_uaf() {
     TEST_HEADER("M-14", "MEDIUM", "Type-erased unique_ptr UAF");
 
     struct HeavyObject {
         int data[64];
         HeavyObject() { std::fill(std::begin(data), std::end(data), 0xDEAD); }
     };
 
     auto up = std::make_unique<HeavyObject>();
     int* raw = &up->data[10];
 
     std::cout << "  Before release: " << std::hex << *raw << std::dec << std::endl;
 
     HeavyObject* released = up.release();
     delete released;
 
     // UAF: raw still points into the deleted HeavyObject
     std::cout << "  After delete (UAF): " << std::hex << *raw << std::dec << std::endl;  // [M-14] UAF HERE
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // M-15: UAF via realloc shrink
 // ---------------------------------------------------------------------------
 void vuln_m15_realloc_shrink_uaf() {
     TEST_HEADER("M-15", "MEDIUM", "realloc shrink causes dangling pointer");
 
     int* arr = (int*)malloc(100 * sizeof(int));
     for (int i = 0; i < 100; i++) arr[i] = i;
 
     int* tail_ptr = &arr[90];
     std::cout << "  Before realloc: tail_ptr = " << *tail_ptr << std::endl;
 
     // realloc to smaller size — tail region is conceptually freed
     int* new_arr = (int*)realloc(arr, 10 * sizeof(int));
 
     // If realloc moved the block, arr and tail_ptr are both dangling
     // Even if not moved, tail_ptr is beyond the valid region
     if (new_arr != arr) {
         // UAF: arr/tail_ptr are dangling
         std::cout << "  After realloc moved (UAF): " << *tail_ptr << std::endl;  // [M-15] UAF HERE
     } else {
         // Out-of-bounds but same block — still logically UAF
         std::cout << "  After realloc same place (logical UAF): " << *tail_ptr << std::endl;  // [M-15] UAF HERE
     }
     free(new_arr);
     g_vuln_triggered++;
 }
 
 
 // ============================================================================
 //  SECTION 3: COMPLEX UAF VULNERABILITIES (C-01 to C-15)
 // ============================================================================
 
 // ---------------------------------------------------------------------------
 // C-01: UAF through polymorphic dispatch (vtable corruption)
 // ---------------------------------------------------------------------------
 class Animal {
 public:
     virtual ~Animal() = default;
     virtual std::string speak() const = 0;
     virtual int legs() const = 0;
 };
 
 class Dog : public Animal {
     std::string name_;
 public:
     Dog(const std::string& n) : name_(n) {}
     std::string speak() const override { return name_ + " says: Woof!"; }
     int legs() const override { return 4; }
 };
 
 class Cat : public Animal {
     int lives_;
 public:
     Cat(int lives) : lives_(lives) {}
     std::string speak() const override { return "Meow! (lives=" + std::to_string(lives_) + ")"; }
     int legs() const override { return 4; }
 };
 
 void vuln_c01_vtable_uaf() {
     TEST_HEADER("C-01", "COMPLEX", "Polymorphic dispatch UAF (vtable corruption)");
 
     Animal* zoo[3];
     zoo[0] = new Dog("Rex");
     zoo[1] = new Cat(9);
     zoo[2] = new Dog("Buddy");
 
     std::cout << "  Before delete: " << zoo[1]->speak() << std::endl;
 
     delete zoo[1];
 
     // Allocate something else that might reuse the memory
     char* overwrite = new char[sizeof(Cat)];
     memset(overwrite, 0x41, sizeof(Cat));
 
     // UAF: virtual dispatch through deleted object, vtable is corrupted
     std::cout << "  After delete (UAF vtable): " << zoo[1]->speak() << std::endl;  // [C-01] UAF HERE
 
     delete[] overwrite;
     delete zoo[0];
     delete zoo[2];
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // C-02: UAF through observer pattern — observer deleted but still registered
 // ---------------------------------------------------------------------------
 class EventBus;
 
 class Observer {
 public:
     int id;
     Observer(int i) : id(i) {}
     virtual ~Observer() = default;
     virtual void on_event(const std::string& event) {
         std::cout << "    Observer " << id << " received: " << event << std::endl;
     }
 };
 
 class EventBus {
     std::vector<Observer*> observers_;
 public:
     void subscribe(Observer* obs) {
         observers_.push_back(obs);
     }
     void unsubscribe(Observer* obs) {
         observers_.erase(
             std::remove(observers_.begin(), observers_.end(), obs),
             observers_.end()
         );
     }
     void publish(const std::string& event) {
         for (auto* obs : observers_) {
             obs->on_event(event);  // potential UAF if observer is deleted
         }
     }
 };
 
 void vuln_c02_observer_pattern_uaf() {
     TEST_HEADER("C-02", "COMPLEX", "Observer pattern UAF — deleted but still subscribed");
 
     EventBus bus;
     auto* obs1 = new Observer(1);
     auto* obs2 = new Observer(2);
     auto* obs3 = new Observer(3);
 
     bus.subscribe(obs1);
     bus.subscribe(obs2);
     bus.subscribe(obs3);
 
     bus.publish("first event");
 
     // Delete obs2 but FORGET to unsubscribe
     delete obs2;
 
     // UAF: bus still holds pointer to deleted obs2
     bus.publish("second event");  // [C-02] UAF HERE — obs2->on_event called
 
     delete obs1;
     delete obs3;
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // C-03: UAF through callback / std::function with captured raw pointer
 // ---------------------------------------------------------------------------
 class AsyncProcessor {
     std::vector<std::function<void()>> callbacks_;
 public:
     void register_callback(std::function<void()> cb) {
         callbacks_.push_back(std::move(cb));
     }
     void process_all() {
         for (auto& cb : callbacks_) {
             cb();
         }
     }
 };
 
 struct DataContext {
     int value;
     std::string label;
     DataContext(int v, const std::string& l) : value(v), label(l) {}
     void print() {
         std::cout << "    DataContext: " << label << " = " << value << std::endl;
     }
 };
 
 void vuln_c03_callback_capture_uaf() {
     TEST_HEADER("C-03", "COMPLEX", "Callback with captured raw pointer UAF");
 
     AsyncProcessor processor;
 
     DataContext* ctx = new DataContext(42, "alpha");
 
     // Register callback that captures raw pointer
     processor.register_callback([ctx]() {
         ctx->print();  // UAF if ctx is deleted before process_all()
     });
 
     std::cout << "  Registered callback." << std::endl;
 
     // Delete context before callbacks fire
     delete ctx;
 
     // UAF: callback invokes method on deleted object
     processor.process_all();  // [C-03] UAF HERE
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // C-04: UAF through multi-threaded race condition
 // ---------------------------------------------------------------------------
 void vuln_c04_thread_race_uaf() {
     TEST_HEADER("C-04", "COMPLEX", "Multi-threaded race condition UAF");
 
     int* shared_data = new int(12345);
     std::atomic<bool> ready{false};
     std::atomic<bool> deleted{false};
 
     // Reader thread
     std::thread reader([&]() {
         while (!ready.load()) std::this_thread::yield();
         // Might read after main thread deletes
         std::this_thread::sleep_for(std::chrono::microseconds(10));
         if (!deleted.load()) {
             std::cout << "  Reader (possibly UAF): " << *shared_data << std::endl;  // [C-04] UAF HERE
         }
     });
 
     // Main thread: signal ready then delete
     ready.store(true);
     std::this_thread::sleep_for(std::chrono::microseconds(5));
     delete shared_data;
     deleted.store(true);
 
     reader.join();
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // C-05: UAF through custom allocator pool (pool recycles freed object)
 // ---------------------------------------------------------------------------
 template <typename T, size_t PoolSize = 16>
 class SimplePool {
     union Slot {
         T object;
         Slot* next;
         Slot() {}
         ~Slot() {}
     };
     Slot slots_[PoolSize];
     Slot* free_list_;
 public:
     SimplePool() {
         free_list_ = &slots_[0];
         for (size_t i = 0; i < PoolSize - 1; i++) {
             slots_[i].next = &slots_[i + 1];
         }
         slots_[PoolSize - 1].next = nullptr;
     }
 
     T* allocate() {
         if (!free_list_) return nullptr;
         Slot* slot = free_list_;
         free_list_ = free_list_->next;
         return new (&slot->object) T();
     }
 
     void deallocate(T* ptr) {
         ptr->~T();
         Slot* slot = reinterpret_cast<Slot*>(ptr);
         slot->next = free_list_;
         free_list_ = slot;
     }
 };
 
 struct PooledTask {
     int priority;
     char description[64];
     void execute() {
         std::cout << "    Executing task (pri=" << priority << "): " << description << std::endl;
     }
 };
 
 void vuln_c05_pool_recycle_uaf() {
     TEST_HEADER("C-05", "COMPLEX", "Pool allocator recycle UAF");
 
     SimplePool<PooledTask> pool;
 
     PooledTask* task1 = pool.allocate();
     task1->priority = 10;
     strcpy(task1->description, "Critical backup");
 
     PooledTask* saved_ref = task1;
 
     pool.deallocate(task1);
 
     // Pool recycles the slot
     PooledTask* task2 = pool.allocate();
     task2->priority = 1;
     strcpy(task2->description, "Low priority cleanup");
 
     // UAF: saved_ref points to recycled slot now containing different data
     saved_ref->execute();  // [C-05] UAF HERE — reads task2's data through old pointer
     pool.deallocate(task2);
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // C-06: UAF through CRTP + static_cast downcast
 // ---------------------------------------------------------------------------
 template <typename Derived>
 class CRTPBase {
 public:
     void interface_method() {
         static_cast<Derived*>(this)->implementation();
     }
     virtual ~CRTPBase() = default;
 };
 
 class ConcreteA : public CRTPBase<ConcreteA> {
 public:
     int data = 42;
     void implementation() {
         std::cout << "    ConcreteA::implementation data=" << data << std::endl;
     }
 };
 
 class ConcreteB : public CRTPBase<ConcreteB> {
 public:
     std::string info = "hello";
     void implementation() {
         std::cout << "    ConcreteB::implementation info=" << info << std::endl;
     }
 };
 
 void vuln_c06_crtp_downcast_uaf() {
     TEST_HEADER("C-06", "COMPLEX", "CRTP downcast UAF after deletion");
 
     auto* a = new ConcreteA();
     CRTPBase<ConcreteA>* base_ptr = a;
 
     base_ptr->interface_method();  // works fine
 
     delete a;
 
     // Allocate something to potentially reuse memory
     auto* filler = new char[sizeof(ConcreteA)];
     memset(filler, 0xFF, sizeof(ConcreteA));
 
     // UAF: virtual dispatch on deleted object via base pointer
     base_ptr->interface_method();  // [C-06] UAF HERE
 
     delete[] filler;
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // C-07: UAF through self-referential data structure (intrusive list)
 // ---------------------------------------------------------------------------
 struct IntrusiveNode {
     int value;
     IntrusiveNode* prev;
     IntrusiveNode* next;
 
     IntrusiveNode(int v) : value(v), prev(nullptr), next(nullptr) {}
 };
 
 class IntrusiveList {
     IntrusiveNode* head_ = nullptr;
     IntrusiveNode* tail_ = nullptr;
 public:
     void push_back(IntrusiveNode* node) {
         node->prev = tail_;
         node->next = nullptr;
         if (tail_) tail_->next = node;
         else head_ = node;
         tail_ = node;
     }
 
     void remove(IntrusiveNode* node) {
         if (node->prev) node->prev->next = node->next;
         else head_ = node->next;
         if (node->next) node->next->prev = node->prev;
         else tail_ = node->prev;
     }
 
     void traverse() {
         IntrusiveNode* cur = head_;
         while (cur) {
             std::cout << "    Node: " << cur->value << std::endl;
             cur = cur->next;
         }
     }
 
     IntrusiveNode* head() { return head_; }
 };
 
 void vuln_c07_intrusive_list_uaf() {
     TEST_HEADER("C-07", "COMPLEX", "Intrusive list node deletion without proper unlinking");
 
     IntrusiveList list;
     auto* n1 = new IntrusiveNode(100);
     auto* n2 = new IntrusiveNode(200);
     auto* n3 = new IntrusiveNode(300);
 
     list.push_back(n1);
     list.push_back(n2);
     list.push_back(n3);
 
     std::cout << "  Before deletion:" << std::endl;
     list.traverse();
 
     // Delete n2 WITHOUT removing from list first
     delete n2;
 
     // UAF: traversal will follow dangling next/prev pointers through deleted n2
     std::cout << "  After deletion (UAF during traversal):" << std::endl;
     list.traverse();  // [C-07] UAF HERE — n1->next points to freed n2
 
     delete n1;
     delete n3;
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // C-08: UAF through move semantics + stale this pointer in method chain
 // ---------------------------------------------------------------------------
 class ChainableBuilder {
 public:
     std::string* data_;
     ChainableBuilder() : data_(new std::string("initial")) {}
     ~ChainableBuilder() { delete data_; }
 
     ChainableBuilder(ChainableBuilder&& other) noexcept : data_(other.data_) {
         other.data_ = nullptr;
     }
 
     ChainableBuilder& operator=(ChainableBuilder&& other) noexcept {
         delete data_;
         data_ = other.data_;
         other.data_ = nullptr;
         return *this;
     }
 
     ChainableBuilder& append(const std::string& s) {
         if (data_) *data_ += s;
         return *this;
     }
 
     std::string result() const {
         return data_ ? *data_ : "(null)";
     }
 };
 
 ChainableBuilder make_builder() {
     ChainableBuilder b;
     b.append("_built");
     return b;
 }
 
 void vuln_c08_move_chain_uaf() {
     TEST_HEADER("C-08", "COMPLEX", "Move semantics stale reference UAF");
 
     ChainableBuilder b1;
     b1.append("_hello");
     std::string* stale_ref = nullptr;
 
     {
         ChainableBuilder b2;
         b2.append("_world");
 
         auto* temp = new std::string("temporary");
         stale_ref = temp;
         b2 = std::move(b1);  // b1 is now moved-from
         delete temp;
     }
     // b2 destroyed here, which destroys old b1's data
 
     // UAF: stale_ref points to deleted string
     if (stale_ref) {
         std::cout << "  Stale ref (UAF): " << *stale_ref << std::endl;  // [C-08] UAF HERE
     }
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // C-09: UAF through signal/slot pattern with raw pointers
 // ---------------------------------------------------------------------------
 class Signal {
     struct SlotEntry {
         void* receiver;
         void (*handler)(void*, int);
     };
     std::vector<SlotEntry> slots_;
 public:
     void connect(void* receiver, void (*handler)(void*, int)) {
         slots_.push_back({receiver, handler});
     }
 
     void emit(int value) {
         for (auto& slot : slots_) {
             slot.handler(slot.receiver, value);
         }
     }
 };
 
 class Receiver {
 public:
     int state = 0;
     static void handle_signal(void* self, int value) {
         auto* r = static_cast<Receiver*>(self);
         r->state += value;
         std::cout << "    Receiver state = " << r->state << std::endl;
     }
 };
 
 void vuln_c09_signal_slot_uaf() {
     TEST_HEADER("C-09", "COMPLEX", "Signal/slot pattern UAF — receiver deleted");
 
     Signal sig;
     auto* recv1 = new Receiver();
     auto* recv2 = new Receiver();
 
     sig.connect(recv1, &Receiver::handle_signal);
     sig.connect(recv2, &Receiver::handle_signal);
 
     sig.emit(10);
 
     // Delete recv1 without disconnecting
     delete recv1;
 
     // UAF: signal emits to deleted receiver
     sig.emit(20);  // [C-09] UAF HERE
 
     delete recv2;
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // C-10: UAF through producer-consumer with shared buffer
 // ---------------------------------------------------------------------------
 struct SharedRingBuffer {
     int* data;
     size_t capacity;
     std::atomic<size_t> write_idx{0};
     std::atomic<size_t> read_idx{0};
 
     SharedRingBuffer(size_t cap) : capacity(cap) {
         data = new int[cap];
     }
     ~SharedRingBuffer() {
         delete[] data;
     }
 
     bool push(int val) {
         size_t w = write_idx.load();
         if ((w - read_idx.load()) >= capacity) return false;
         data[w % capacity] = val;
         write_idx.store(w + 1);
         return true;
     }
 
     bool pop(int& val) {
         size_t r = read_idx.load();
         if (r >= write_idx.load()) return false;
         val = data[r % capacity];
         read_idx.store(r + 1);
         return true;
     }
 };
 
 void vuln_c10_producer_consumer_uaf() {
     TEST_HEADER("C-10", "COMPLEX", "Producer-consumer shared buffer UAF");
 
     auto* buffer = new SharedRingBuffer(64);
 
     // Producer thread
     std::thread producer([buffer]() {
         for (int i = 0; i < 100; i++) {
             buffer->push(i);  // might access freed buffer
             std::this_thread::sleep_for(std::chrono::microseconds(1));
         }
     });
 
     // Main thread deletes buffer while producer is running
     std::this_thread::sleep_for(std::chrono::microseconds(50));
     delete buffer;  // [C-10] UAF SETUP — producer still accessing buffer
 
     producer.join();
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // C-11: UAF through recursive tree deletion with parent pointer
 // ---------------------------------------------------------------------------
 struct TreeNode {
     int value;
     TreeNode* left = nullptr;
     TreeNode* right = nullptr;
     TreeNode* parent = nullptr;
 
     TreeNode(int v, TreeNode* p = nullptr) : value(v), parent(p) {}
 };
 
 TreeNode* build_tree() {
     auto* root = new TreeNode(50);
     root->left = new TreeNode(25, root);
     root->right = new TreeNode(75, root);
     root->left->left = new TreeNode(10, root->left);
     root->left->right = new TreeNode(35, root->left);
     root->right->left = new TreeNode(60, root->right);
     return root;
 }
 
 void delete_subtree(TreeNode* node) {
     if (!node) return;
     delete_subtree(node->left);
     delete_subtree(node->right);
     delete node;
 }
 
 void vuln_c11_tree_parent_uaf() {
     TEST_HEADER("C-11", "COMPLEX", "Tree parent pointer UAF after subtree deletion");
 
     TreeNode* root = build_tree();
     TreeNode* left_child = root->left;
     TreeNode* grandchild = root->left->right;  // value=35, parent=left_child
 
     std::cout << "  Grandchild parent value: " << grandchild->parent->value << std::endl;
 
     // Delete left subtree
     delete_subtree(left_child);
 
     // UAF: root->left is dangling
     std::cout << "  Root->left after delete (UAF): " << root->left->value << std::endl;  // [C-11] UAF HERE
 
     // Cleanup remaining
     delete_subtree(root->right);
     delete root;
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // C-12: UAF through variant visitor with pointer member
 // ---------------------------------------------------------------------------
 struct ImageData {
     int width, height;
     uint8_t* pixels;
     ImageData(int w, int h) : width(w), height(h) {
         pixels = new uint8_t[w * h * 4];
         memset(pixels, 128, w * h * 4);
     }
     ~ImageData() { delete[] pixels; }
     ImageData(const ImageData&) = delete;
     ImageData& operator=(const ImageData&) = delete;
     ImageData(ImageData&& o) noexcept : width(o.width), height(o.height), pixels(o.pixels) {
         o.pixels = nullptr;
     }
     ImageData& operator=(ImageData&& o) noexcept {
         delete[] pixels;
         width = o.width; height = o.height; pixels = o.pixels;
         o.pixels = nullptr;
         return *this;
     }
 };
 
 struct TextData {
     char* content;
     TextData(const char* s) {
         content = new char[strlen(s) + 1];
         strcpy(content, s);
     }
     ~TextData() { delete[] content; }
     TextData(const TextData&) = delete;
     TextData& operator=(const TextData&) = delete;
     TextData(TextData&& o) noexcept : content(o.content) { o.content = nullptr; }
     TextData& operator=(TextData&& o) noexcept {
         delete[] content;
         content = o.content;
         o.content = nullptr;
         return *this;
     }
 };
 
 void vuln_c12_variant_uaf() {
     TEST_HEADER("C-12", "COMPLEX", "Variant type reassignment causes UAF on cached inner pointer");
 
     using MediaType = std::variant<ImageData, TextData>;
 
     MediaType media = ImageData(100, 100);
     uint8_t* pixel_cache = std::get<ImageData>(media).pixels;
 
     std::cout << "  Pixel cache before: " << (int)pixel_cache[0] << std::endl;
 
     // Reassign variant — destroys ImageData, constructs TextData
     media = TextData("Hello variant world");
 
     // UAF: pixel_cache points to ImageData's deleted pixel buffer
     std::cout << "  Pixel cache after variant switch (UAF): " << (int)pixel_cache[0] << std::endl;  // [C-12] UAF HERE
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // C-13: UAF through coroutine-like state machine with dangling continuation
 // ---------------------------------------------------------------------------
 class StateMachine {
 public:
     struct State {
         std::string name;
         std::function<State*()> transition;
     };
 
     std::vector<State*> states_;
     State* current_ = nullptr;
 public:
     State* add_state(const std::string& name, std::function<State*()> trans) {
         auto* s = new State{name, std::move(trans)};
         states_.push_back(s);
         return s;
     }
 
     void set_current(State* s) { current_ = s; }
 
     void step() {
         if (current_ && current_->transition) {
             std::cout << "    Transitioning from: " << current_->name << std::endl;
             current_ = current_->transition();
             if (current_)
                 std::cout << "    Transitioned to: " << current_->name << std::endl;
         }
     }
 
     void remove_state(State* s) {
         auto it = std::find(states_.begin(), states_.end(), s);
         if (it != states_.end()) states_.erase(it);
         delete s;
     }
 
     ~StateMachine() {
         for (auto* s : states_) delete s;
     }
 };
 
 void vuln_c13_state_machine_uaf() {
     TEST_HEADER("C-13", "COMPLEX", "State machine dangling continuation UAF");
 
     StateMachine sm;
 
     auto* idle = sm.add_state("IDLE", nullptr);
     auto* processing = sm.add_state("PROCESSING", nullptr);
     auto* done = sm.add_state("DONE", nullptr);
 
     // Set transitions using raw pointers to other states
     idle->transition = [processing]() -> StateMachine::State* {
         return processing;  // captures raw pointer
     };
     // This line won't compile with the private State struct — let's redesign
 
     processing->transition = [done]() -> StateMachine::State* {
         return done;
     };
 
     sm.set_current(idle);
     sm.step();  // IDLE -> PROCESSING (OK)
 
     // Delete 'done' state while 'processing' still references it
     sm.remove_state(done);
 
     // UAF: processing's transition returns dangling pointer to deleted 'done'
     sm.step();  // [C-13] UAF HERE — accesses deleted 'done' state
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // C-14: UAF through shared_ptr weak_ptr circular reference + force delete
 // ---------------------------------------------------------------------------
 class Company;
 
 class Employee {
 public:
     std::string name;
     Company* company;  // raw pointer for illustration
     Employee(const std::string& n) : name(n), company(nullptr) {}
     void work() {
         std::cout << "    " << name << " working at company" << std::endl;
     }
 };
 
 class Company {
 public:
     std::string name;
     std::vector<Employee*> employees;
 
     Company(const std::string& n) : name(n) {}
 
     void add_employee(Employee* e) {
         employees.push_back(e);
         e->company = this;
     }
 
     void fire_all() {
         for (auto* e : employees) {
             delete e;
         }
         employees.clear();
     }
 
     void announce() {
         std::cout << "  Company " << name << " employees:" << std::endl;
         for (auto* e : employees) {
             e->work();  // UAF if employee was deleted elsewhere
         }
     }
 };
 
 void vuln_c14_ownership_confusion_uaf() {
     TEST_HEADER("C-14", "COMPLEX", "Ownership confusion — double management UAF");
 
     Company corp("TechCorp");
     auto* alice = new Employee("Alice");
     auto* bob = new Employee("Bob");
     auto* charlie = new Employee("Charlie");
 
     corp.add_employee(alice);
     corp.add_employee(bob);
     corp.add_employee(charlie);
 
     corp.announce();
 
     // External code deletes Bob directly
     delete bob;
 
     // Company still has Bob in its list
     corp.announce();  // [C-14] UAF HERE — iterates over deleted bob
 
     // Company's fire_all will double-free bob
     // Only delete remaining valid employees
     delete alice;
     delete charlie;
     corp.employees.clear();
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // C-15: UAF through thread-local + thread pool interaction
 // ---------------------------------------------------------------------------
 class ThreadLocalCache {
     struct CacheEntry {
         int* data;
         size_t size;
     };
     static thread_local std::vector<CacheEntry> cache_;
 
 public:
     static int* allocate(size_t count) {
         int* p = new int[count];
         cache_.push_back({p, count});
         return p;
     }
 
     static void clear_cache() {
         for (auto& entry : cache_) {
             delete[] entry.data;
         }
         cache_.clear();
     }
 
     // Returns a pointer from cache — might be stale
     static int* get_cached(size_t index) {
         if (index < cache_.size()) return cache_[index].data;
         return nullptr;
     }
 };
 
 thread_local std::vector<ThreadLocalCache::CacheEntry> ThreadLocalCache::cache_;
 
 void vuln_c15_thread_local_uaf() {
     TEST_HEADER("C-15", "COMPLEX", "Thread-local cache UAF across clear");
 
     int* p1 = ThreadLocalCache::allocate(10);
     int* p2 = ThreadLocalCache::allocate(20);
 
     p1[0] = 111;
     p2[0] = 222;
 
     std::cout << "  Before clear: p1[0]=" << p1[0] << " p2[0]=" << p2[0] << std::endl;
 
     // Clear cache — deletes all cached allocations
     ThreadLocalCache::clear_cache();
 
     // UAF: p1 and p2 are dangling
     std::cout << "  After clear (UAF): p1[0]=" << p1[0] << std::endl;  // [C-15] UAF HERE
     std::cout << "  After clear (UAF): p2[0]=" << p2[0] << std::endl;  // [C-15] UAF HERE (secondary)
     g_vuln_triggered++;
 }
 
 
 // ============================================================================
 //  SECTION 4: ADDITIONAL MEDIUM-COMPLEX VARIANTS (MC-01 to MC-10)
 // ============================================================================
 
 // ---------------------------------------------------------------------------
 // MC-01: UAF through std::function with deleted captured object
 // ---------------------------------------------------------------------------
 class Logger {
     std::string prefix_;
 public:
     Logger(const std::string& p) : prefix_(p) {}
     void log(const std::string& msg) {
         std::cout << "    [" << prefix_ << "] " << msg << std::endl;
     }
 };
 
 void vuln_mc01_function_object_uaf() {
     TEST_HEADER("MC-01", "MEDIUM-COMPLEX", "std::function with deleted captured object");
 
     std::function<void(const std::string&)> log_fn;
     {
         auto* logger = new Logger("APP");
         log_fn = [logger](const std::string& msg) {
             logger->log(msg);
         };
         log_fn("before delete");
         delete logger;
     }
     // UAF: log_fn still captures deleted logger
     log_fn("after delete — UAF");  // [MC-01] UAF HERE
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // MC-02: UAF through custom smart pointer with release bug
 // ---------------------------------------------------------------------------
 template <typename T>
 class BuggySmartPtr {
     T* ptr_;
     int* ref_count_;
 public:
     BuggySmartPtr(T* p = nullptr) : ptr_(p), ref_count_(new int(1)) {}
 
     BuggySmartPtr(const BuggySmartPtr& other) : ptr_(other.ptr_), ref_count_(other.ref_count_) {
         (*ref_count_)++;
     }
 
     BuggySmartPtr& operator=(const BuggySmartPtr& other) {
         if (this != &other) {
             release();
             ptr_ = other.ptr_;
             ref_count_ = other.ref_count_;
             (*ref_count_)++;
         }
         return *this;
     }
 
     ~BuggySmartPtr() { release(); }
 
     void release() {
         if (ref_count_ && --(*ref_count_) == 0) {
             delete ptr_;
             delete ref_count_;
             ptr_ = nullptr;
             ref_count_ = nullptr;
         }
         // BUG: doesn't null out ptr_ when ref_count > 0 after decrement
         // This isn't the UAF itself, but contributes to confusion
     }
 
     T* get() const { return ptr_; }
     T& operator*() const { return *ptr_; }
     T* operator->() const { return ptr_; }
 };
 
 void vuln_mc02_buggy_smart_ptr_uaf() {
     TEST_HEADER("MC-02", "MEDIUM-COMPLEX", "Buggy smart pointer UAF");
 
     int* raw = nullptr;
     {
         BuggySmartPtr<int> sp1(new int(42));
         raw = sp1.get();
         {
             BuggySmartPtr<int> sp2 = sp1;  // ref_count = 2
             std::cout << "  sp2: " << *sp2 << std::endl;
         }  // sp2 destroyed, ref_count = 1
         std::cout << "  sp1: " << *sp1 << std::endl;
     }  // sp1 destroyed, ref_count = 0, object deleted
 
     // UAF: raw points to deleted object
     std::cout << "  raw after smart ptrs destroyed (UAF): " << *raw << std::endl;  // [MC-02] UAF HERE
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // MC-03: UAF through emplace_back + reference invalidation
 // ---------------------------------------------------------------------------
 struct Connection {
     int fd;
     std::string address;
     Connection(int f, const std::string& a) : fd(f), address(a) {}
     void send(const std::string& msg) {
         std::cout << "    Sending to " << address << " (fd=" << fd << "): " << msg << std::endl;
     }
 };
 
 void vuln_mc03_emplace_invalidation_uaf() {
     TEST_HEADER("MC-03", "MEDIUM-COMPLEX", "emplace_back reference invalidation UAF");
 
     std::vector<Connection> connections;
     connections.emplace_back(1, "192.168.1.1");
 
     Connection& first_ref = connections[0];  // reference to first element
     first_ref.send("hello");
 
     // Add many more connections causing reallocation
     for (int i = 2; i <= 100; i++) {
         connections.emplace_back(i, "192.168.1." + std::to_string(i));
     }
 
     // UAF: first_ref is dangling after vector reallocation
     first_ref.send("goodbye — UAF");  // [MC-03] UAF HERE
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // MC-04: UAF through graph adjacency list with node deletion
 // ---------------------------------------------------------------------------
 struct GraphNode {
     int id;
     std::vector<GraphNode*> neighbors;
     GraphNode(int i) : id(i) {}
     void print_neighbors() {
         std::cout << "    Node " << id << " neighbors:";
         for (auto* n : neighbors) {
             std::cout << " " << n->id;  // UAF if neighbor deleted
         }
         std::cout << std::endl;
     }
 };
 
 void vuln_mc04_graph_adjacency_uaf() {
     TEST_HEADER("MC-04", "MEDIUM-COMPLEX", "Graph adjacency list UAF");
 
     auto* n1 = new GraphNode(1);
     auto* n2 = new GraphNode(2);
     auto* n3 = new GraphNode(3);
     auto* n4 = new GraphNode(4);
 
     n1->neighbors = {n2, n3};
     n2->neighbors = {n1, n3, n4};
     n3->neighbors = {n1, n2};
     n4->neighbors = {n2};
 
     n1->print_neighbors();
 
     // Delete n3 without removing from adjacency lists
     delete n3;
 
     // UAF: n1 and n2 still have n3 in their neighbor lists
     n1->print_neighbors();  // [MC-04] UAF HERE — accesses deleted n3
     n2->print_neighbors();  // [MC-04] UAF HERE — accesses deleted n3
 
     delete n1;
     delete n2;
     delete n4;
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // MC-05: UAF through async task queue with deleted context
 // ---------------------------------------------------------------------------
 class TaskQueue {
     std::queue<std::pair<std::function<void()>, std::string>> tasks_;
 public:
     void enqueue(std::function<void()> task, const std::string& desc) {
         tasks_.push({std::move(task), desc});
     }
 
     void run_all() {
         while (!tasks_.empty()) {
             auto [task, desc] = std::move(tasks_.front());
             tasks_.pop();
             std::cout << "    Running: " << desc << std::endl;
             task();
         }
     }
 };
 
 struct SessionContext {
     int session_id;
     std::string user;
     std::vector<int> data;
 
     SessionContext(int id, const std::string& u) : session_id(id), user(u) {
         data.resize(100, 0);
     }
 
     void process() {
         std::cout << "      Processing session " << session_id
                   << " for " << user << " (" << data.size() << " items)" << std::endl;
     }
 };
 
 void vuln_mc05_async_task_context_uaf() {
     TEST_HEADER("MC-05", "MEDIUM-COMPLEX", "Async task queue with deleted context UAF");
 
     TaskQueue queue;
     auto* session = new SessionContext(101, "admin");
 
     queue.enqueue([session]() {
         session->process();  // [MC-05] UAF HERE if session deleted before run
     }, "process session 101");
 
     queue.enqueue([session]() {
         std::cout << "      Session " << session->session_id << " complete" << std::endl;
     }, "finalize session 101");
 
     // Delete session before running tasks
     delete session;
 
     // UAF: tasks reference deleted session
     queue.run_all();  // [MC-05] UAF HERE
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // MC-06: UAF through container of unique_ptr with raw pointer alias
 // ---------------------------------------------------------------------------
 void vuln_mc06_unique_ptr_container_uaf() {
     TEST_HEADER("MC-06", "MEDIUM-COMPLEX", "Container of unique_ptr with raw pointer alias UAF");
 
     std::vector<std::unique_ptr<std::string>> strings;
     strings.push_back(std::make_unique<std::string>("alpha"));
     strings.push_back(std::make_unique<std::string>("beta"));
     strings.push_back(std::make_unique<std::string>("gamma"));
 
     std::string* beta_raw = strings[1].get();  // raw alias
     std::cout << "  Before erase: " << *beta_raw << std::endl;
 
     // Erase element — unique_ptr deletes the string
     strings.erase(strings.begin() + 1);
 
     // UAF: beta_raw points to deleted string
     std::cout << "  After erase (UAF): " << *beta_raw << std::endl;  // [MC-06] UAF HERE
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // MC-07: UAF through RAII guard scope mismatch
 // ---------------------------------------------------------------------------
 class MutexGuard {
     std::mutex& mtx_;
     int* protected_data_;
 public:
     MutexGuard(std::mutex& m, int* data) : mtx_(m), protected_data_(data) {
         mtx_.lock();
     }
     ~MutexGuard() {
         mtx_.unlock();
     }
     int* data() { return protected_data_; }
 };
 
 void vuln_mc07_raii_scope_uaf() {
     TEST_HEADER("MC-07", "MEDIUM-COMPLEX", "RAII guard scope mismatch UAF");
 
     std::mutex mtx;
     int* shared = new int(42);
     int* cached = nullptr;
 
     {
         MutexGuard guard(mtx, shared);
         cached = guard.data();
         std::cout << "  Inside guard: " << *cached << std::endl;
         delete shared;  // delete while still "protected" by guard
     }
 
     // UAF: cached points to deleted memory
     std::cout << "  After guard scope (UAF): " << *cached << std::endl;  // [MC-07] UAF HERE
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // MC-08: UAF through std::set with custom comparator using pointer data
 // ---------------------------------------------------------------------------
 struct PriorityItem {
     int* priority;
     std::string name;
     PriorityItem(int p, const std::string& n) : name(n) {
         priority = new int(p);
     }
 };
 
 struct PriorityComparator {
     bool operator()(const PriorityItem* a, const PriorityItem* b) const {
         return *(a->priority) < *(b->priority);
     }
 };
 
 void vuln_mc08_set_comparator_uaf() {
     TEST_HEADER("MC-08", "MEDIUM-COMPLEX", "Set with comparator accessing freed priority");
 
     std::set<PriorityItem*, PriorityComparator> pq;
 
     auto* item1 = new PriorityItem(3, "low");
     auto* item2 = new PriorityItem(1, "high");
     auto* item3 = new PriorityItem(2, "medium");
 
     pq.insert(item1);
     pq.insert(item2);
     pq.insert(item3);
 
     // Delete priority value of item2
     delete item2->priority;
     item2->priority = nullptr;
 
     // UAF: set operations (find/insert) will invoke comparator on item2
     auto* item4 = new PriorityItem(0, "urgent");
     pq.insert(item4);  // [MC-08] UAF HERE — comparator dereferences deleted priority
 
     for (auto* item : pq) {
         if (item->priority)
             std::cout << "    " << item->name << " (pri=" << *(item->priority) << ")" << std::endl;
         delete item->priority;
         delete item;
     }
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // MC-09: UAF through unordered_map rehash with pointer keys
 // ---------------------------------------------------------------------------
 void vuln_mc09_unordered_map_rehash_uaf() {
     TEST_HEADER("MC-09", "MEDIUM-COMPLEX", "unordered_map element reference invalidation");
 
     std::unordered_map<int, std::string> map;
     map[1] = "one";
     map[2] = "two";
     map[3] = "three";
 
     std::string* ref = &map[2];
     std::cout << "  Before rehash: " << *ref << std::endl;
 
     // Force rehash
     map.reserve(10000);
 
     // After rehash, existing pointers/references may be invalidated
     std::cout << "  After rehash (potential UAF): " << *ref << std::endl;  // [MC-09] UAF HERE
     g_vuln_triggered++;
 }
 
 // ---------------------------------------------------------------------------
 // MC-10: UAF through recursive callback with deletion mid-recursion
 // ---------------------------------------------------------------------------
 struct RecursiveProcessor {
     int depth;
     int* result_buffer;
     std::function<void(RecursiveProcessor*, int)> on_complete;
 
     RecursiveProcessor(int d) : depth(d) {
         result_buffer = new int[depth];
         for (int i = 0; i < depth; i++) result_buffer[i] = i;
     }
     ~RecursiveProcessor() { delete[] result_buffer; }
 
     void process(int level) {
         if (level >= depth) {
             if (on_complete) on_complete(this, level);
             return;
         }
         result_buffer[level] *= 2;
         std::cout << "    Level " << level << ": " << result_buffer[level] << std::endl;
         process(level + 1);
     }
 };
 
 void vuln_mc10_recursive_callback_uaf() {
     TEST_HEADER("MC-10", "MEDIUM-COMPLEX", "Recursive callback deletes object mid-processing");
 
     auto* proc = new RecursiveProcessor(5);
     int* external_ref = proc->result_buffer;
 
     proc->on_complete = [&proc](RecursiveProcessor* self, int level) {
         std::cout << "    Complete at level " << level << ", deleting processor" << std::endl;
         delete self;  // deletes the processor during its own execution
         proc = nullptr;
     };
 
     proc->process(0);  // [MC-10] UAF HERE — object deletes itself during recursion
 
     // external_ref is now dangling
     if (external_ref) {
         std::cout << "  External ref after deletion (UAF): " << external_ref[0] << std::endl;  // [MC-10] UAF secondary
     }
     g_vuln_triggered++;
 }
 
 
 // ============================================================================
 //  SECTION 5: SAFE FUNCTIONS (NO VULNERABILITIES — false positive tests)
 // ============================================================================
 
 // These should NOT be flagged by the SAST tool
 
 void safe_01_proper_null_after_delete() {
     int* p = new int(42);
     delete p;
     p = nullptr;
     // SAFE: p is null, no dereference
     if (p) std::cout << *p << std::endl;
 }
 
 void safe_02_unique_ptr_ownership() {
     auto up = std::make_unique<int>(100);
     int val = *up;
     up.reset();
     // SAFE: only val (copy) is used, not the pointer
     std::cout << "  Safe val: " << val << std::endl;
 }
 
 void safe_03_shared_ptr_proper() {
     auto sp1 = std::make_shared<int>(200);
     auto sp2 = sp1;  // shared ownership
     sp1.reset();
     // SAFE: sp2 still owns the object
     std::cout << "  Safe shared: " << *sp2 << std::endl;
 }
 
 void safe_04_vector_copy() {
     std::vector<int> v = {1, 2, 3, 4, 5};
     int copy = v[2];
     v.clear();
     // SAFE: copy is a value, not a pointer/reference
     std::cout << "  Safe copy: " << copy << std::endl;
 }
 
 void safe_05_raii_cleanup() {
     struct Guard {
         int* p;
         Guard(int* ptr) : p(ptr) {}
         ~Guard() { delete p; }
     };
     Guard g(new int(300));
     std::cout << "  Safe RAII: " << *g.p << std::endl;
     // SAFE: g.p is deleted in destructor, no use after
 }
 
 void safe_06_move_with_check() {
     auto up1 = std::make_unique<int>(400);
     auto up2 = std::move(up1);
     // SAFE: checking before use
     if (up1) {
         std::cout << *up1 << std::endl;
     } else {
         std::cout << "  Safe: up1 is null after move" << std::endl;
     }
     std::cout << "  Safe: up2 = " << *up2 << std::endl;
 }
 
 void safe_07_scope_contained() {
     {
         int* p = new int(500);
         std::cout << "  Safe scoped: " << *p << std::endl;
         delete p;
     }
     // SAFE: p is out of scope, cannot be accessed
 }
 
 void safe_08_vector_reserve_then_push() {
     std::vector<int> v;
     v.reserve(1000);
     v.push_back(1);
     int* p = &v[0];
     // SAFE: reserved enough, push_back won't reallocate
     for (int i = 2; i <= 100; i++) v.push_back(i);
     std::cout << "  Safe reserved: " << *p << std::endl;
 }
 
 void run_safe_tests() {
     std::cout << "\n====== SAFE CODE (should NOT be flagged) ======" << std::endl;
     safe_01_proper_null_after_delete();
     safe_02_unique_ptr_ownership();
     safe_03_shared_ptr_proper();
     safe_04_vector_copy();
     safe_05_raii_cleanup();
     safe_06_move_with_check();
     safe_07_scope_contained();
     safe_08_vector_reserve_then_push();
     std::cout << "  All safe tests passed." << std::endl;
 }
 
 
 // ============================================================================
 //  SECTION 6: DECOY PATTERNS (tricky but safe, to test false positive rate)
 // ============================================================================
 
 void decoy_01_delete_and_reassign() {
     int* p = new int(10);
     delete p;
     p = new int(20);  // reassigned before use
     std::cout << "  Decoy reassign: " << *p << std::endl;  // SAFE
     delete p;
 }
 
 void decoy_02_conditional_delete_all_paths() {
     int* p = new int(30);
     bool flag = (rand() % 2 == 0);
     if (flag) {
         delete p;
         p = nullptr;
     }
     if (p) {
         std::cout << "  Decoy conditional: " << *p << std::endl;  // SAFE
         delete p;
     }
 }
 
 void decoy_03_swap_then_use_new() {
     int* a = new int(40);
     int* b = new int(50);
     std::swap(a, b);
     delete b;  // deletes original 'a'
     std::cout << "  Decoy swap: " << *a << std::endl;  // SAFE — a now holds original b
     delete a;
 }
 
 void decoy_04_shared_ptr_aliasing() {
     auto sp = std::make_shared<int>(60);
     int* raw = sp.get();
     auto sp2 = sp;
     sp.reset();
     std::cout << "  Decoy shared alias: " << *raw << std::endl;  // SAFE — sp2 keeps alive
     sp2.reset();
     // raw is now dangling but not accessed
 }
 
 void decoy_05_optional_with_value() {
     std::optional<int> opt = 70;
     int val = *opt;
     opt.reset();
     std::cout << "  Decoy optional: " << val << std::endl;  // SAFE — val is a copy
 }
 
 void run_decoy_tests() {
     std::cout << "\n====== DECOY PATTERNS (tricky but safe) ======" << std::endl;
     decoy_01_delete_and_reassign();
     decoy_02_conditional_delete_all_paths();
     decoy_03_swap_then_use_new();
     decoy_04_shared_ptr_aliasing();
     decoy_05_optional_with_value();
     std::cout << "  All decoy tests passed." << std::endl;
 }
 
 
 // ============================================================================
 //  MAIN: Run all vulnerability tests
 // ============================================================================
 
 int main(int argc, char* argv[]) {
     std::cout << "================================================================" << std::endl;
     std::cout << "  UAF Vulnerability Test Suite for AI-Driven SAST" << std::endl;
     std::cout << "  WARNING: This program contains intentional vulnerabilities!" << std::endl;
     std::cout << "================================================================" << std::endl;
 
     // Determine which tests to run
     bool run_simple = true;
     bool run_medium = true;
     bool run_complex = true;
     bool run_medium_complex = true;
     bool run_safe = true;
     bool run_decoy = true;
 
     if (argc > 1) {
         std::string mode = argv[1];
         run_simple = run_medium = run_complex = run_medium_complex = run_safe = run_decoy = false;
         if (mode == "simple") run_simple = true;
         else if (mode == "medium") run_medium = true;
         else if (mode == "complex") run_complex = true;
         else if (mode == "mc") run_medium_complex = true;
         else if (mode == "safe") { run_safe = true; run_decoy = true; }
         else if (mode == "all") {
             run_simple = run_medium = run_complex = run_medium_complex = run_safe = run_decoy = true;
         }
     }
 
     // ---- SIMPLE ----
     if (run_simple) {
         std::cout << "\n====== SIMPLE UAF VULNERABILITIES ======" << std::endl;
         vuln_s01_direct_delete_deref();
         vuln_s02_free_then_write();
         vuln_s03_array_delete_access();
         // S-04 skipped by default (double free may crash)
         // vuln_s04_double_free();
         vuln_s05_struct_member_after_delete();
     }
 
     // ---- MEDIUM ----
     if (run_medium) {
         std::cout << "\n====== MEDIUM UAF VULNERABILITIES ======" << std::endl;
         vuln_m01_returned_dangling_ptr();
         vuln_m02_conditional_uaf(true);
         vuln_m03_vector_iterator_invalidation();
         vuln_m04_string_internal_buffer();
         vuln_m05_map_erase_dangling();
         vuln_m06_shared_raw_mix();
         vuln_m07_unique_ptr_reset();
         vuln_m08_swap_dangling();
         vuln_m09_exception_path_uaf();
         vuln_m10_aliased_loop_uaf();
         vuln_m11_lambda_capture_uaf();
         vuln_m12_placement_new_uaf();
         vuln_m13_deque_invalidation();
         vuln_m14_any_type_erasure_uaf();
         vuln_m15_realloc_shrink_uaf();
     }
 
     // ---- COMPLEX ----
     if (run_complex) {
         std::cout << "\n====== COMPLEX UAF VULNERABILITIES ======" << std::endl;
         // C-01 skipped by default (vtable corruption may segfault)
         // vuln_c01_vtable_uaf();
         vuln_c02_observer_pattern_uaf();
         vuln_c03_callback_capture_uaf();
         vuln_c04_thread_race_uaf();
         vuln_c05_pool_recycle_uaf();
         // C-06 skipped by default (vtable corruption may segfault)
         // vuln_c06_crtp_downcast_uaf();
         vuln_c07_intrusive_list_uaf();
         vuln_c08_move_chain_uaf();
         vuln_c09_signal_slot_uaf();
         vuln_c10_producer_consumer_uaf();
         vuln_c11_tree_parent_uaf();
         vuln_c12_variant_uaf();
         vuln_c13_state_machine_uaf();
         vuln_c14_ownership_confusion_uaf();
         vuln_c15_thread_local_uaf();
     }
 
     // ---- MEDIUM-COMPLEX ----
     if (run_medium_complex) {
         std::cout << "\n====== MEDIUM-COMPLEX UAF VULNERABILITIES ======" << std::endl;
         vuln_mc01_function_object_uaf();
         vuln_mc02_buggy_smart_ptr_uaf();
         vuln_mc03_emplace_invalidation_uaf();
         vuln_mc04_graph_adjacency_uaf();
         vuln_mc05_async_task_context_uaf();
         vuln_mc06_unique_ptr_container_uaf();
         vuln_mc07_raii_scope_uaf();
         vuln_mc08_set_comparator_uaf();
         vuln_mc09_unordered_map_rehash_uaf();
         vuln_mc10_recursive_callback_uaf();
     }
 
     // ---- SAFE & DECOY ----
     if (run_safe) run_safe_tests();
     if (run_decoy) run_decoy_tests();
 
     // Summary
     std::cout << "\n================================================================" << std::endl;
     std::cout << "  SUMMARY" << std::endl;
     std::cout << "  Total tests run:        " << g_test_counter << std::endl;
     std::cout << "  Vulnerabilities triggered: " << g_vuln_triggered << std::endl;
     std::cout << "  Safe/Decoy tests:       " << (run_safe ? 8 : 0) + (run_decoy ? 5 : 0) << std::endl;
     std::cout << "================================================================" << std::endl;
 
     return 0;
 }
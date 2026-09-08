# Prospective Spring concurrent LRU lifecycle: source review

This is a new full navigation operation on an existing corpus, prepared before any three-arm model trials. No upstream Java code, tests, benchmarks or builds were executed. The source snapshot, case, complete criteria, review and experiment inputs must be frozen before launch. This review does not establish model quality or cost savings and does not change historical tasks or gates.

## Pin and scope

Repository: `spring-projects/spring-framework`, commit `4c8c6409a27a62ab163d3b6196ad862b7c835440`. The existing `/tmp/columbus-spring-navigation-source.zip` is a **spring-core subtree fixture**, not a complete repository archive. Its SHA-256 is `68572527bfad750c2ab2c55dcbab1324568a4584d0d122cc3a4dfac8c139bd0c`: 2,174,897 compressed bytes, 1,166 regular files, 7,120,331 uncompressed bytes. All ZIP members match the local spring-core source. The local untracked `.columbus` index is not in the ZIP.

The implementation, test and assertion-helper bytes were independently compared with both their ZIP members and pinned Git blobs:

| Repository-relative file inside the fixture | SHA-256 | Physical lines |
| --- | --- | ---: |
| `src/main/java/org/springframework/util/ConcurrentLruCache.java` | `58ee866e0b18b50749eb36579a81dae974518aa02a495fbbf99a0de92ad47e9a` | 598 |
| `src/test/java/org/springframework/util/ConcurrentLruCacheTests.java` | `60ed16448d89f9c998d48ad554f2c033b0a97ca08260fa81309ced239d10b54a` | 111 |
| `src/main/java/org/springframework/util/Assert.java` | `70f8bec8b969dd22e280724a3f85788a6d4b9baa8f84176fb85c217607944590` | 652 |

Source headers retain Apache-2.0 notices. The subtree ZIP does not include a standalone license; upstream repository-root `LICENSE.txt`, outside this ZIP, has SHA-256 `56dfc19e0dc836e30177332f73e8e6fbc297941acf3d906eec6eaaa46c2c452a`. Publication must not describe that file as part of the unchanged source fixture. Detailed scope, inventory hash and two proposed graph controls are recorded in `source.json`.

## Navigation and fair scoring contract

Case `java-concurrent-lru-cache-lifecycle` has six finding IDs and 24 clauses. Its visible question names the behavior to discover, not source paths, line ranges or private literal markers. Discovery must connect public retrieval/removal/clear operations with insertion, read/write buffers, status coordination, nested tasks and queue/state helpers. This is not a request to reformat a supplied range. All six representative witnesses are in the implementation, but their full explanations require navigating substantially separated helpers; the tests and `Assert` corroborate boundaries.

Every positive clause in `criteria.json` must be supported by correct final prose or an actual supporting quote; reading a file in the trace alone does not cover an omitted fact. Equivalent wording and shared context across findings are accepted. Contradictions fail the affected requirement. Explicit scope exclusions are contradiction boundaries, not a demand to recite out-of-scope warnings. The six finding IDs and zero-based clause indices are fixed together; no post-result omission or simplification is justified by smaller output.

Each finding requires a repository-relative path and one contiguous source quote within a contiguous range of at most 40 physical lines. The representative quote need not contain every supporting branch. Other inspected behavior must be synthesized in the explanation; ellipses, stitched snippets, invented braces or ranges that fail to contain the actual quote are not substitutes. The historical grader's indentation-insensitive check remains unchanged. Its `call_lines` field holds reviewed mechanism anchors, not a claim that the task enumerates callers. The collector must separately require the exact six IDs and the complete semantic gate.

Source-level concurrency boundaries matter. Do not reward descriptions that turn `putIfAbsent` into single-flight generation, make buffered recency globally exact, equate deferred accounting with map size, or turn `clear()` into a globally atomic map-empty barrier. Conversely, this task does not require proving arbitrary concurrent schedules, formally auditing the ring-buffer algorithm, analyzing the generator's own side effects/reentrancy, or implementing a fix. The numerical buffer/drain bounds and counter-update semantics are explicitly requested, not hidden extras.

## entry-generation

Clauses: `entry-generation[0]`–`[4]`. Representative range: implementation lines 100–126, 27 physical lines. Marker and reviewed call: `put(key, value);`, line 107.

```java
	public V get(K key) {
		if (this.capacity == 0) {
			return this.generator.apply(key);
		}
		Node<K, V> node = this.cache.get(key);
		if (node == null) {
			V value = this.generator.apply(key);
			put(key, value);
			return value;
		}
		processRead(node);
		return node.getValue();
	}

	private void put(K key, V value) {
		Assert.notNull(key, "key must not be null");
		Assert.notNull(value, "value must not be null");
		CacheEntry<V> cacheEntry = new CacheEntry<>(value, CacheEntryState.ACTIVE);
		Node<K, V> node = new Node<>(key, cacheEntry);
		Node<K, V> prior = this.cache.putIfAbsent(node.key, node);
		if (prior == null) {
			processWrite(new AddTask(node));
		}
		else {
			processRead(prior);
		}
	}
```

Additional support: implementation 81–92, 128–154, 359–364 and 513–515; `Assert` 114–119 and 179–184. A losing miss discards its new node for caching but still returns its local generated value. Positive-capacity insertion rejects a null value before the competing-key check. Zero capacity bypasses that assertion and directly returns a null generator result. Uncaught generator failures do not reach this invocation's insertion. Non-null keys and generator are stated assumptions; do not add invalid-key or null-generator requirements.

## read-recency

Clauses: `read-recency[0]`–`[3]`. Representative range: implementation lines 435–449, 15 physical lines. Marker and anchor: `this.evictionQueue.moveToBack(node);`, line 445.

```java
		private void drainReadBuffer(int bufferIndex) {
			final long writeCount = this.recordedCount.get(bufferIndex);
			for (int i = 0; i < MAX_DRAIN_COUNT; i++) {
				final int index = (int) (this.readCount[bufferIndex] & BUFFER_INDEX_MASK);
				final AtomicReferenceArray<@Nullable Node<K, V>> buffer = this.buffers[bufferIndex];
				final Node<K, V> node = buffer.get(index);
				if (node == null) {
					break;
				}
				buffer.lazySet(index, null);
				this.evictionQueue.moveToBack(node);
				this.readCount[bufferIndex]++;
			}
			this.processedCount.lazySet(bufferIndex, writeCount);
		}
```

Additional support: 110, 123–133, 367–424, 542–563 and 584–589. Four thread-selected buffers contain 128 positions each. Pending work uses the captured pre-increment count minus processed count; `< 32` returns **delayable**, despite the caller's `drainRequested` local name. Draining visits four stripes and handles at most 64 positions per stripe, stopping on null. The processed counter becomes the recorded-count snapshot even when the loop stops early. Queue membership and already-last checks prevent this helper from resurrecting an absent node or pointlessly relinking the tail. These details do not establish a globally exact concurrent access order.

## drain-coordination

Clauses: `drain-coordination[0]`–`[3]`. Representative range: implementation lines 128–154, 27 physical lines. Marker and reviewed call: `this.writeOperations.drain();`, line 147.

```java
	private void processRead(Node<K, V> node) {
		boolean drainRequested = this.readOperations.recordRead(node);
		DrainStatus status = this.drainStatus.get();
		if (status.shouldDrainBuffers(drainRequested)) {
			drainOperations();
		}
	}

	private void processWrite(Runnable task) {
		this.writeOperations.add(task);
		this.drainStatus.lazySet(DrainStatus.REQUIRED);
		drainOperations();
	}

	private void drainOperations() {
		if (this.evictionLock.tryLock()) {
			try {
				this.drainStatus.lazySet(DrainStatus.PROCESSING);
				this.readOperations.drain();
				this.writeOperations.drain();
			}
			finally {
				this.drainStatus.compareAndSet(DrainStatus.PROCESSING, DrainStatus.IDLE);
				this.evictionLock.unlock();
			}
		}
	}
```

Additional support: 64–72, 312–350 and 454–479. IDLE drains only when the read is not delayable; REQUIRED always does; PROCESSING suppresses another read-triggered attempt. A failed tryLock neither waits nor launches work elsewhere. The successful drain orders reads before at most 16 write tasks. Its conditional status reset preserves a REQUIRED value installed by a concurrent writer. No worker thread or timer is created. Generator and map operations occur outside this maintenance lock, so the lock must not be described as a global cache-operation mutex.

## insertion-eviction

Clauses: `insertion-eviction[0]`–`[3]`. Representative range: implementation lines 269–286, 18 physical lines. Marker and reviewed call: `markAsRemoved(node);`, line 284.

```java
		public void run() {
			currentSize.lazySet(currentSize.get() + 1);
			if (this.node.get().isActive()) {
				evictionQueue.add(this.node);
				evictEntries();
			}
		}

		private void evictEntries() {
			while (currentSize.get() > capacity) {
				Node<K, V> node = evictionQueue.poll();
				if (node == null) {
					return;
				}
				cache.remove(node.key, node);
				markAsRemoved(node);
			}
		}
```

Additional support: 66–70, 114–126, 177–179, 203–212, 353–364 and 525–563. AddTask increments bookkeeping before checking active state, which matters when map insertion and later removal precede task execution. Queue insertion is unique and at the back; polling removes the front. Conditional map removal protects a replacement node under the same key. The removed-state CAS retains the value and decrements internal accounting. Deferred currentSize and public map size are not synonyms; neither immediate capacity enforcement under contention nor perfectly current LRU order follows from this code.

## key-removal

Clauses: `key-removal[0]`–`[2]`. Representative range: implementation lines 229–254, 26 physical lines. Marker and reviewed call: `processWrite(new RemovalTask(node));`, line 235.

```java
	public boolean remove(K key) {
		Node<K, V> node = this.cache.remove(key);
		if (node == null) {
			return false;
		}
		markForRemoval(node);
		processWrite(new RemovalTask(node));
		return true;
	}

	/**
	 * Transition the node from the {@code active} state to the {@code pending removal} state,
	 * if the transition is valid.
	 */
	private void markForRemoval(Node<K, V> node) {
		while (true) {
			CacheEntry<V> current = node.get();
			if (!current.isActive()) {
				return;
			}
			CacheEntry<V> pendingRemoval = new CacheEntry<>(current.value, CacheEntryState.PENDING_REMOVAL);
			if (node.compareAndSet(current, pendingRemoval)) {
				return;
			}
		}
	}
```

Additional support: 104–111, 136–154, 203–212, 293–305, 513–515 and 591–595. Map removal is immediate; queue/state cleanup is a scheduled task that may be deferred. PENDING_REMOVAL is conditional on ACTIVE, not an overwrite of any current state. RemovalTask unlinks membership and marks removed. Neither transition clears the stored value, so an already-held node can still supply a retrieval's value. No cancellation guarantee should be invented.

## clear-and-observation

Clauses: `clear-and-observation[0]`–`[3]`. Representative range: implementation lines 184–198, 15 physical lines. Marker and reviewed call: `this.writeOperations.drainAll();`, line 193.

```java
	public void clear() {
		this.evictionLock.lock();
		try {
			Node<K, V> node;
			while ((node = this.evictionQueue.poll()) != null) {
				this.cache.remove(node.key, node);
				markAsRemoved(node);
			}
			this.readOperations.clear();
			this.writeOperations.drainAll();
		}
		finally {
			this.evictionLock.unlock();
		}
	}
```

Additional support: 100–126, 160–179, 203–220, 269–286, 426–433 and 474–479. Clear uses blocking lock acquisition, not tryLock. It removes queued nodes, clears read slots without resetting the counters, and executes all pending write tasks afterward. It never directly invokes map.clear(). A pending addition can therefore be processed after the initial queue-removal pass; concurrent map mutations are not all excluded by this lock. This is a concrete source-ordering limitation, not a requirement to prove a particular adversarial execution or call the whole class incorrect.

Public size/contains inspect the map; capacity and deprecated sizeLimit expose configured capacity. `ConcurrentLruCacheTests` lines 34–55 corroborate zero-capacity nonretention; 57–73 cover sequential insertion and eviction; 75–91 cover removal; 93–109 cover clear and reuse. Those tests do not exercise competing generation, every-hit recency, held-node removal, or pending-write/concurrent clear scenarios. They must not be presented as runtime verification performed for this review.

## Prelaunch graph controls and validation limits

Two meaningful source relationships are proposed in `source.json`: retrieval calls private insertion at implementation line 107, and the locked maintenance coordinator calls the nested write drain at line 147. Both connect an entry-stage mechanism to a relevant helper and are useful navigation evidence. Preparation must resolve exact saved-graph IDs and require successful archive-backed evidence for the pinned path and source bytes. Merely listing an available graph, returning no source, or offering a command is not a passing control. Static edges are not the semantic oracle.

The six representative ranges contain 128 physical lines in aggregate; each is independently below 40. They are witnesses, not prescribed ranges in the model question. Preparation must validate JSON, exact ID/criterion correspondence, all 24 clauses, literal witness bytes and the unchanged citation grader before freezing. Such deterministic checks establish a well-formed task, not observed model success, semantic completeness, or savings. Full-quality and actual-cost acceptance criteria remain the responsibility of the preregistered three-arm protocol.

## Prepared-graph relationship review, before launch and freeze

The prepared, unchanged Java graph has SHA-256 `b624d888e8a35f55c6f43f3255c2b21878d56e75d1e764442e9571d1fa998b23`. Its two initially suggested source calls are **not resolved graph edges**: line 107 retains an unresolved reference with reason `generic declaring-type substitution requires semantic analysis`; line 147 retains an unresolved reference with reason `complex, this or super receiver unsupported`. The source behavior remains required by the unchanged case and criteria, but those references cannot be counted as delivered resolved relationships.

`relationships.json` instead retains all eight actual `calls` edges whose source path is the cache production file, with their exact complete source/target IDs, path and physical line. Each was compared with the pinned source and the source/target declaration ranges. All are relevant to the requested lifecycle, so the valid set is not narrowed to an arbitrary pair that could reject a different useful relationship. This is a prospectively reviewed set, not a post-model adjustment.

| Source call site | Actual graph target | Physical line | Reviewed role and bounds |
| --- | --- | ---: | --- |
| Three-argument cache constructor | `WriteOperations` class | 91 | Constructor 85–92 creates the task queue implementation at 454–480. |
| `ReadOperations.recordRead` | `ReadOperations.getBufferIndex` method | 408 | Recording 407–415 chooses its thread-indexed stripe through 402–405. |
| `processRead` | `drainOperations` method | 132 | Read scheduling 128–134 reaches the lock-protected maintenance method at 142–154 when status requests draining. |
| `processWrite` | `drainOperations` method | 139 | Write scheduling 136–140 reaches that same maintenance method after enqueueing and setting REQUIRED. |
| `put` | `AddTask` class | 121 | Successful insertion 114–126 constructs the addition task at 260–287. |
| `put` | `processWrite` method | 121 | The same expression schedules that task through 136–140. |
| `remove` | `RemovalTask` class | 235 | Present-key removal 229–237 constructs the cleanup task at 293–306. |
| `remove` | `processWrite` method | 235 | The same expression schedules cleanup through 136–140 after marking pending removal. |

The constructor-allocation edges target class nodes in this archive, not fabricated constructor-method IDs. At lines 121 and 235 the allocation and outer scheduling call are separate target relationships at the same physical site. All eight edges have archive confidence `heuristic`; their participating nodes are Java AST declarations with `partial: false`. This establishes reviewed static navigation evidence, not dynamic dispatch, a complete call graph, or semantic correctness of any eventual answer. Successful frozen-runtime/archive responses with the expected source hashes are still required by prelaunch and run-level recognition controls.

The case and criteria were not modified for this graph review. Their SHA-256 values remain `0d194626537769afcac3b5928d847579d4b8e4810a468818f2003c268fa4f1f8` and `0cd6104e7d1334cc7fc3f1804301946a0c9c07b28528ecdcabc5a7f24ec66e24`, respectively. All six literal representative witnesses already passed the unchanged citation grader, and an over-40-line negative was rejected; that mechanical check did not substitute for the 24-clause semantic gate.

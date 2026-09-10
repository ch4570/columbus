package synthetic

import jakarta.persistence.Entity
import jakarta.persistence.Table
import org.springframework.cache.annotation.CacheEvict
import org.springframework.kafka.annotation.KafkaListener
import org.springframework.stereotype.Service
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RestController

@RestController
class Controller(private val executor: Executor) {
    @PostMapping("/synthetic/items")
    fun create() = executor.execute()
}

class Executor(private val useCase: UseCase) {
    fun execute() = useCase.perform()
}

interface UseCase {
    fun perform()
}

@Service
class Handler(private val repository: Repository) : UseCase {
    @CacheEvict(cacheNames = ["synthetic-items"], allEntries = true)
    override fun perform() = repository.save()
}

class Repository {
    fun save() {}
}

@Entity
@Table(name = "synthetic_item", schema = "demo")
class Item

class Listener(private val executor: Executor) {
    @KafkaListener(topics = ["synthetic-events"], groupId = "synthetic-consumer")
    fun consume() = executor.execute()
}

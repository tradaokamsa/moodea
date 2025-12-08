package utils

import (
	"sync"
	"runtime"
)

// WorkerPool executes tasks concurrently with a fixed number of workers
type WorkerPool struct {
	workers int
	tasks   chan func()
	wg      sync.WaitGroup
}

// NewWorkerPool creates a new worker pool with the specified number of workers
func NewWorkerPool(workers int) *WorkerPool {
	if workers <= 0 {
		workers = runtime.NumCPU()
	}
	wp := &WorkerPool{
		workers: workers,
		tasks:   make(chan func()),
	}
	wp.Start()
	return wp
}

func (wp *WorkerPool) Start() {
	for i := 0; i < wp.workers; i++ {
		go func() {
			for task := range wp.tasks {
				task()
				wp.wg.Done()
			}
		}()
	}
}

// Submit adds a task to the worker pool
func (wp *WorkerPool) Submit(task func()) {
	wp.wg.Add(1)
	wp.tasks <- task
}

// Wait waits for all tasks to complete and closes the pool
func (wp *WorkerPool) Wait() {
	close(wp.tasks)
	wp.wg.Wait()
}

// BatchProcess processes items in batches concurrently
func BatchProcess[T any](items []T, batchSize int, processor func([]T) error) error {
	if batchSize <= 0 {
		batchSize = 1
	}
	workers := runtime.NumCPU()
	wp := NewWorkerPool(workers)

	var (
		errOnce sync.Once
		retErr  error
	)

	for i := 0; i < len(items); i += batchSize {
		start := i
		end := i + batchSize
		if end > len(items) {
			end = len(items)
		}
		chunk := items[start:end]

		wp.Submit(func() {
			if err := processor(chunk); err != nil {
				errOnce.Do(func() {
					retErr = err
				})
			}
		})
	}
	wp.Wait()
	return retErr
}
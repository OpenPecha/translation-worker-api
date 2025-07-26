#!/usr/bin/env python3
"""
Performance Comparison: Sequential vs Parallel Translation
Shows the dramatic speed improvement with parallel processing
"""
import asyncio
import time
from typing import List
import sys
import os

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def simulate_sequential_translation(segments: List[str], delay_per_segment: float = 1.0) -> dict:
    """
    Simulate sequential translation processing
    """
    print(f"🐌 SEQUENTIAL: Processing {len(segments)} segments one by one...")
    start_time = time.time()
    
    results = []
    for i, segment in enumerate(segments):
        print(f"  Processing segment {i+1}/{len(segments)}...")
        time.sleep(delay_per_segment)  # Simulate AI API call delay
        results.append(f"Translated: {segment}")
    
    total_time = time.time() - start_time
    return {
        "method": "Sequential",
        "segments": len(segments),
        "total_time": total_time,
        "segments_per_second": len(segments) / total_time,
        "results": results
    }

async def simulate_parallel_translation(segments: List[str], delay_per_segment: float = 1.0, max_workers: int = 10) -> dict:
    """
    Simulate parallel translation processing using asyncio
    """
    print(f"🚀   Processing {len(segments)} segments with {max_workers} workers...")
    start_time = time.time()
    
    async def translate_segment(index: int, segment: str) -> tuple:
        """Translate a single segment"""
        await asyncio.sleep(delay_per_segment)  # Simulate AI API call delay
        return index, f"Translated: {segment}"
    
    # Create tasks for all segments
    tasks = [translate_segment(i, segment) for i, segment in enumerate(segments)]
    
    # Execute all tasks in parallel
    results_with_index = await asyncio.gather(*tasks)
    
    # Sort by index to maintain order
    results_with_index.sort(key=lambda x: x[0])
    results = [result for _, result in results_with_index]
    
    total_time = time.time() - start_time
    return {
        "method": "Parallel",
        "segments": len(segments),
        "total_time": total_time,
        "segments_per_second": len(segments) / total_time,
        "max_workers": max_workers,
        "results": results
    }

def print_performance_comparison(sequential_result: dict, parallel_result: dict):
    """
    Print a detailed performance comparison
    """
    print("\n" + "="*60)
    print("📊 PERFORMANCE COMPARISON RESULTS")
    print("="*60)
    
    print(f"\n🐌 SEQUENTIAL PROCESSING:")
    print(f"   • Total time: {sequential_result['total_time']:.2f} seconds")
    print(f"   • Segments/second: {sequential_result['segments_per_second']:.2f}")
    print(f"   • Method: One segment at a time (blocking)")
    
    print(f"\n🚀 PARALLEL PROCESSING:")
    print(f"   • Total time: {parallel_result['total_time']:.2f} seconds")
    print(f"   • Segments/second: {parallel_result['segments_per_second']:.2f}")
    print(f"   • Workers: {parallel_result['max_workers']}")
    print(f"   • Method: All segments simultaneously")
    
    # Calculate improvement
    speed_improvement = sequential_result['total_time'] / parallel_result['total_time']
    time_saved = sequential_result['total_time'] - parallel_result['total_time']
    efficiency_gain = ((sequential_result['total_time'] - parallel_result['total_time']) / sequential_result['total_time']) * 100
    
    print(f"\n⚡ PERFORMANCE GAIN:")
    print(f"   • Speed improvement: {speed_improvement:.1f}x faster")
    print(f"   • Time saved: {time_saved:.2f} seconds")
    print(f"   • Efficiency gain: {efficiency_gain:.1f}%")
    
    # Practical examples
    print(f"\n🎯 PRACTICAL IMPACT:")
    if speed_improvement >= 10:
        print(f"   • 🚀 MASSIVE improvement: 10-minute job → {10/speed_improvement:.1f} minutes")
    elif speed_improvement >= 5:
        print(f"   • ⚡ MAJOR improvement: 5-minute job → {5/speed_improvement:.1f} minutes")
    elif speed_improvement >= 2:
        print(f"   • 📈 SIGNIFICANT improvement: 2-minute job → {2/speed_improvement:.1f} minutes")
    
    print(f"   • Large document (1000 segments): {1000*1/sequential_result['segments_per_second']:.0f}s → {1000*1/parallel_result['segments_per_second']:.0f}s")
    
    # Order verification
    print(f"\n🔍 ORDER PRESERVATION:")
    if sequential_result['results'] == parallel_result['results']:
        print(f"   • ✅ Perfect order preservation maintained")
    else:
        print(f"   • ❌ Order not preserved (this shouldn't happen!)")

async def main():
    """
    Run the performance comparison demonstration
    """
    print("🎯 PARALLEL TRANSLATION PERFORMANCE DEMO")
    print("=========================================")
    print("This demonstrates the speed difference between sequential and parallel processing")
    print("")
    
    # Create test segments
    test_segments = [
        "བཀྲ་ཤིས་བདེ་ལེགས།",
        "ཁྱོད་ག་འདྲ་འདུག",
        "ཞོགས་པ་བདེ་ལེགས།", 
        "ང་རང་བདེ་པོ་ཡིན།",
        "ཁྱོད་རང་ག་རེ་བྱེད་ཀྱི་ཡོད།",
        "དེ་རིང་ཐལ་བ་ཡག་པོ་འདུག",
        "མ་ཕྱི་ཚུགས་པར་མཇལ་རྒྱུ་ཡིན།",
        "ཁ་ལག་ཁྱེར་རྒྱུ་མ་བརྗེད།"
    ]
    
    # Simulate AI API delay (1 second per segment)
    api_delay = 1.0
    max_workers = min(len(test_segments), 10)
    
    print(f"📋 Test Configuration:")
    print(f"   • Segments to translate: {len(test_segments)}")
    print(f"   • Simulated AI API delay: {api_delay} second per segment")
    print(f"   • Parallel workers: {max_workers}")
    print("")
    
    # Run sequential processing
    print("Starting sequential processing...")
    sequential_result = simulate_sequential_translation(test_segments, api_delay)
    
    print("\nStarting parallel processing...")
    parallel_result = await simulate_parallel_translation(test_segments, api_delay, max_workers)
    
    # Show comparison
    print_performance_comparison(sequential_result, parallel_result)
    
    print(f"\n🎉 CONCLUSION:")
    print(f"Parallel processing provides {sequential_result['total_time']/parallel_result['total_time']:.1f}x speed improvement")
    print(f"while maintaining perfect segment order!")
    print("")
    print(f"🔥 In your translation system, this means:")
    print(f"   • Multi-batch translations complete {sequential_result['total_time']/parallel_result['total_time']:.1f}x faster")
    print(f"   • Better resource utilization") 
    print(f"   • Shorter wait times for users")
    print(f"   • Higher throughput capacity")

if __name__ == "__main__":
    asyncio.run(main()) 
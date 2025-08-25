#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import aiohttp
import aiodns
import time
import os
import random
from typing import List, Tuple

class AsyncGroupedDomainResolver:
    def __init__(self, dns_servers=None, timeout=3, concurrency_per_group=50, verbose=True):
        self.dns_servers = dns_servers or [
            '8.8.8.8', '1.1.1.1', '223.5.5.5', '119.29.29.29',
            '208.67.222.222', '9.9.9.9', '149.112.112.112', '8.8.4.4',
            '1.0.0.1', '223.6.6.6', "45.11.45.11", "4.2.2.2"
        ]
        self.timeout = timeout
        self.concurrency_per_group = concurrency_per_group
        self.verbose = verbose

    async def fetch_domains(self, url: str) -> List[str]:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as resp:
                text = await resp.text()
        domains = [line.strip().lower() for line in text.split("\n") if line and not line.startswith("#")]
        return domains

    async def resolve_domain(self, domain: str, resolver: aiodns.DNSResolver) -> bool:
        try:
            await resolver.query(domain, 'A')
            return True
        except:
            return False

    async def resolve_group(self, domains: List[str], dns_server: str) -> Tuple[List[str], List[str]]:
        """解析单个 DNS 下的一组域名"""
        valid, failed = [], []
        semaphore = asyncio.Semaphore(self.concurrency_per_group)
        resolver = aiodns.DNSResolver(nameservers=[dns_server], timeout=self.timeout)

        async def worker(domain):
            async with semaphore:
                if await self.resolve_domain(domain, resolver):
                    valid.append(domain)
                else:
                    failed.append(domain)

        await asyncio.gather(*[worker(d) for d in domains])
        return valid, failed

    async def resolve_in_round(self, domains: List[str], round_num: int) -> Tuple[List[str], List[str]]:
        """一次性尝试所有 DNS，每轮随机分配域名到 DNS"""
        if self.verbose:
            print(f"\n🚀 第 {round_num} 轮解析: {len(domains)} 个域名, 使用 {len(self.dns_servers)} 个DNS", flush=True)

        # 随机打乱域名列表
        domains_shuffled = domains[:]
        random.shuffle(domains_shuffled)

        # 随机分配到 DNS
        domain_groups = [[] for _ in self.dns_servers]
        for domain in domains_shuffled:
            dns_index = random.randint(0, len(self.dns_servers) - 1)
            domain_groups[dns_index].append(domain)

        tasks = [
            self.resolve_group(group, dns)
            for group, dns in zip(domain_groups, self.dns_servers) if group
        ]
        results = await asyncio.gather(*tasks)

        all_valid, all_failed = [], []
        for valid, failed in results:
            all_valid.extend(valid)
            all_failed.extend(failed)

        if self.verbose:
            success_rate = (len(all_valid) / len(domains)) * 100 if domains else 0
            print(f"✅ 第 {round_num} 轮完成: 成功 {len(all_valid)}, 失败 {len(all_failed)}, 成功率 {success_rate:.2f}%", flush=True)

        return all_valid, all_failed

    async def batch_resolve(self, domains: List[str], output_success: str, output_failed: str):
        start_time = time.time()
        remaining_domains = domains[:]
        all_valid = []
        round_num = 1

        while remaining_domains:
            valid, failed = await self.resolve_in_round(remaining_domains, round_num)
            all_valid.extend(valid)
            remaining_domains = failed

            min_success_count = 10  # 阈值
            if len(valid) < min_success_count:
                if self.verbose:
                    print(f"⚠️ 第 {round_num} 轮成功 {len(valid)} 个域名，低于阈值 {min_success_count}，任务终止。", flush=True)
                break

            round_num += 1

        total_elapsed = time.time() - start_time
        final_success_rate = (len(all_valid) / len(domains)) * 100 if domains else 0

        self.save_domains(all_valid, output_success)
        self.save_domains(remaining_domains, output_failed)

        if self.verbose:
            print("\n🎯 任务完成!", flush=True)
            print(f"📊 总域名数: {len(domains)}", flush=True)
            print(f"✅ 有效域名: {len(all_valid)}", flush=True)
            print(f"❌ 最终失败: {len(remaining_domains)}", flush=True)
            print(f"📈 成功率: {final_success_rate:.2f}%", flush=True)
            print(f"⏱ 总耗时: {total_elapsed:.1f}s", flush=True)
            print(f"💾 成功结果: {output_success}", flush=True)
            print(f"💾 失败结果: {output_failed}", flush=True)

    def save_domains(self, domains: List[str], filename: str):
        os.makedirs(os.path.dirname(filename) or '.', exist_ok=True)
        with open(filename, 'w', encoding='utf-8') as f:
            for d in domains:
                f.write(d + "\n")


async def main():
    SOURCE_URL = "https://raw.githubusercontent.com/privacy-protection-tools/anti-AD/master/anti-ad-domains.txt"
    OUTPUT_SUCCESS = "./output/valid_domains.txt"
    OUTPUT_FAILED = "./output/failed_domains.txt"

    resolver = AsyncGroupedDomainResolver(timeout=3, concurrency_per_group=50, verbose=True)
    print("🔍 正在获取域名列表...", flush=True)
    domains = await resolver.fetch_domains(SOURCE_URL)
    print(f"📦 获取到 {len(domains)} 个域名", flush=True)

    await resolver.batch_resolve(domains, OUTPUT_SUCCESS, OUTPUT_FAILED)


if __name__ == "__main__":
    asyncio.run(main())

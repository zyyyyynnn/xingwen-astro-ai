<script setup lang="ts">
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

const modules = [
  { label: '数据整合', desc: '系外行星候选体与宿主恒星参数整合' },
  { label: '论文获取', desc: '结构化总结与证据链追踪' },
  { label: '推理图谱', desc: 'Claim / Relation / Trace 可视化' },
]
</script>

<template>
  <main class="mx-auto flex min-h-screen max-w-3xl flex-col justify-center px-6 py-16">
    <section class="flex flex-col gap-2">
      <Badge variant="secondary" class="w-fit">国赛级 MVP · 主案例</Badge>
      <h1 class="text-3xl font-semibold tracking-tight text-foreground">
        星文智析 AI 科研工具
      </h1>
      <p class="text-muted-foreground">
        面向系外行星候选体与宿主恒星参数整合的科研协作平台，覆盖数据整合、论文获取、推理与图谱主链路。
      </p>
    </section>

    <Card class="mt-8 shadow-soft">
      <CardHeader>
        <CardTitle>核心模块</CardTitle>
        <CardDescription>主链路稳定优先，证据可信，演示完整。</CardDescription>
      </CardHeader>
      <CardContent class="flex flex-col gap-4">
        <div
          v-for="m in modules"
          :key="m.label"
          class="flex flex-col gap-1 border-b border-border pb-4 last:border-0 last:pb-0"
        >
          <span class="font-medium text-foreground">{{ m.label }}</span>
          <span class="text-sm text-muted-foreground">{{ m.desc }}</span>
        </div>
      </CardContent>
      <CardFooter class="gap-3">
        <Button>开始使用</Button>
        <Button variant="outline">查看文档</Button>
      </CardFooter>
    </Card>

    <p class="mt-6 text-xs text-muted-foreground">
      前端不直连 Qwen、论文源或天文数据源，所有数据通过后端 API 获取。
    </p>
  </main>
</template>

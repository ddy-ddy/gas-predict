<script context="module">
  // 从后端获取example的code数据
  export async function load({ fetch }) {
    const res = await fetch('http://127.0.0.1:5000/example');
    const info = await res.json();
    return {
      props: {
        info,
      },
    };
  }
</script>

<script>
  import { HighlightAuto } from 'svelte-highlight'; //代码高亮
  import bright from 'svelte-highlight/styles/bright';
  import Typewriter from 'svelte-typewriter'; //打字机效果
  import * as echarts from 'echarts'; //原生echarts
  import { Chart } from 'svelte-echarts'; //在svelte中使用echarts
  import { exampleX, exampleY, exampleFunction, description, title } from './variable'; //example的数据

  export let info;
  $: code = info.code;
  let functionName = exampleFunction;
  let x = exampleX;
  let y = exampleY;

  //点击不同数据时数据的变化
  function handleFunctionChoose(tempInfo) {
    functionName = tempInfo[0];
    y = tempInfo[1];
  }

  //echarts的option（主要变量要用$: 表示可变的数据,每当他们依赖的值发生改变时，都会在component更新之前立即运行）
  $: options = {
    tooltip: {
      trigger: 'axis',
      position: function (pt) {
        return [pt[0], '20%'];
      },
    },
    title: {
      left: 'center',
    },
    toolbox: {
      feature: {
        dataZoom: {
          yAxisIndex: 'none',
        },
        restore: {},
        saveAsImage: {},
      },
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: x,
    },
    yAxis: {
      type: 'value',
      boundaryGap: [0, '100%'],
    },
    dataZoom: [
      {
        type: 'inside',
        start: 0,
        end: 100,
      },
      {
        start: 0,
        end: 10,
      },
    ],
    series: [
      {
        name: '概率',
        type: 'line',
        symbol: 'none',
        sampling: 'lttb',
        itemStyle: {
          color: 'rgb(255, 70, 131)',
        },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            {
              offset: 0,
              color: 'rgb(255, 158, 68)',
            },
            {
              offset: 1,
              color: 'rgb(255, 70, 131)',
            },
          ]),
        },
        data: y,
      },
    ],
  };

  //上传的文件
  let fileVar;
  async function submitForm() {
    const dataArray = new FormData();
    dataArray.append('uploadFile', fileVar);
    const res = await fetch('http://127.0.0.1:5000/upload', {
      method: 'POST',
      headers: [['Content-Type', 'multipart/form-data']],
      body: dataArray,
    });
    info = await res.json(); //修改页面的info信息
  }
</script>

<svelte:head>
  {@html bright}
</svelte:head>

<div class="max-w-screen-xl mx-auto px-4 py-4 sm:px-6 lg-px-8">
  <!-- 项目介绍 -->
  <header class="mt-4">
    <h2
      class="font-display font-extrabold text-2xl sm:text-4xl underline decoration-orange-400 underline-offset-4 text-indigo-500 sm:text-center">
      {title}
    </h2>
    <Typewriter interval={80} cascade>
      <ul
        class="flex flex-col sm:place-items-center py-4 list-disc sm:list-none list-inside mx-auto font-body font-bold underline decoration-sky-500/[.33] hover:decoration-sky-600/[.33] decoration-wavy underline-offset-2 text-md sm:text-lg text-indigo-400">
        {#each description as des}
          <li>{des}</li>
        {/each}
      </ul>
    </Typewriter>
  </header>

  <section class="grid grid-cols-1 sm:grid-cols-2 gap-8 mt-4 sm:mt-12 px-2 sm:px-16">
    <!-- grid左边代码展示 -->
    <div class="flex overflow-auto bg-black shadow-xl rounded-xl h-[26rem] lg:h-[36rem]">
      <div class="relative w-full flex flex-col">
        <!-- 3个标志 -->
        <div class="flex h-8 space-x-1.5 px-3 py-3 border-b border-slate-500/30">
          <div class="w-2.5 h-2.5 bg-red-500 rounded-full" />
          <div class="w-2.5 h-2.5 bg-yellow-500 rounded-full" />
          <div class="w-2.5 h-2.5 bg-green-500 rounded-full" />
        </div>
        <!-- 代码 -->
        <div class="min-h-0 flex flex-col">
          <pre class="flex min-h-full text-xs sm:text-sm leading-4">
              <code class="relative block overflow-auto"><HighlightAuto code={code} /></code>
          </pre>
        </div>
      </div>
    </div>
    <!-- grid右边结果展示 -->
    <div class="h-[26rem] lg:h-[36rem]">
      <!-- 函数 -->
      <div class="mb-4 overflow-auto flex flex-row  gap-4 place-content-between">
        {#each info.data as tempInfo, i}
          <div class="hover:bg-gray-300 rounded-md p-2">
            <button
              type="button"
              on:click={handleFunctionChoose(tempInfo)}
              class="font-body group text-sm font-semibold w-full flex flex-col items-center text-indigo-500">
              <img src="/img/{(i % 3) + 1}.svg" class="h-6 w-6 mb-2" alt="svg" />
              {tempInfo[0]}</button>
          </div>
        {/each}
      </div>
      <!-- 数据 -->
      <div class="bg-white rounded-xl shadow-xl">
        <div class="px-4 overflow-auto">
          <div class="container">
            <Chart options={options} />
          </div>
        </div>
        <div class="font-body font-bold text-lg text-center py-2">
          Function: <span class="text-orange-400">{functionName}</span>
        </div>
      </div>
    </div>
  </section>

  <!-- 上传自己的contract -->
  <form
    class="mt-48 sm:mt-4 grid grid-rows-2 justify-items-center gap-2"
    on:submit|preventDefault={submitForm}>
    <input
      type="file"
      class="block text-sm text-indigo-500 pl-16
      file:mr-4 file:py-2 file:px-4
      file:rounded-full file:border-0
      file:text-sm file:font-semibold
      file:bg-indigo-50 file:text-indigo-700
      hover:file:bg-indigo-100"
      bind:files={fileVar} />
    <button
      type="submit"
      class="w-24 btn btn-md font-body bg-gray-800 hover:bg-gray-400 border-gray-400 shadow-2xl"
      >上传</button>
  </form>
</div>

<style>
  .container {
    width: 500px;
    height: 450px;
  }
  pre[data-language='css'] {
    --hljs-background: black;
    --hljs-foreground: #fff;
    --hljs-radius: 8px;
  }
</style>

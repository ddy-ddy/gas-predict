import * as echarts from 'echarts';

// export function echarts(node, option) {
//     const chart = charts.init(node);
//     chart.setOption(option);

//     return {
//         update(option) {

//         }
//     }

// }

// export function chartable(element, options) {
//     const echartsInstance = echarts.init(element);
//     echartsInstance.setOption(options);
//     function handleResize() {
//         echartsInstance.resize();
//     }
//     window.addEventListener("resize", handleResize);
//     return {
//         destroy() {
//             echartsInstance.dispose();
//             window.removeEventListener("resize", handleResize);
//         },
//         update(newOptions) {
//             echartsInstance.setOption(
//                 {
//                     ...options,
//                     ...newOptions
//                 }
//             );
//         },
//     };
// }
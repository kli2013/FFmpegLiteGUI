# FFmpegLiteGUI
　　找 AI 用 python 写的 FFmpeg GUI

　　契机是 HandBrake 又又又又又又又又又换了.NET 10（软件开发框架） ,我的老Windows 10 ltsc 2021 装了.NET 10 ,运行 HandBrake还是要报错, 我当时就在想,一个破 FFmpeg 的外壳, 需要这么追新吗?

　　然后在52pj看到了另外一个 FFmpeg的 gui外壳 https://www.52pojie.cn/forum.php?mod=viewthread&tid=2099752&highlight=FFmpeg

也是用的.NET 10 ,我又用不了

　　我一气之下就气了一下, 借着这个拼接命令的灵感 ,找 ai 根据我以前用的一个bat(里面是我各种FFmpeg命令的 的模版,每次都手动改了goto1234保存在发送文件运行) 写一个简易GUI

第一个版本居然就实现了我大部分的想法

　　后续又和Ai聊了半个月添加了各种功能,感觉已经实现了HandBrake 90% ,启动还快

　　第二页是轻量的mkvtoolnix, 没有实现轨道的默认 语言 这些设置, 只有简单的流复制和转码合并 ,画中画功能是聊了很久才聊成功的, 免费的ai不行,我也不会写代码,找bug都没办法

　　后续也是有点聊不动了,主要代码量有点多了,每次免费ai都偷工减料要我自己替换,不给我一次输出全部的,python的缩进又严格,天天出bug

　　可能不会更新别的功能了,现在的我自己是够用了,在复杂点我都直接去用shotcut了

<img width="1372" height="907" alt="m1" src="https://github.com/user-attachments/assets/48055308-4d0a-421f-9329-aba95a363925" />

<img width="1372" height="907" alt="m3" src="https://github.com/user-attachments/assets/e2bb13cb-fb94-4f16-845c-87c109d9778f" />

20260601更新了一些功能
    1、mpv预览,mpv可以拖动进度条,这样可以填截取时间,
    2、画中画功能添加了简易的绘制框,这样就能代替预览查看主从视频的位置和偏移,绘制和预览的时候会自动应用当前的裁剪属性(锁定绘制比例),应用后会自动更改缩放里的数值,
    如果绘制框没有实时应用新的缩放比例,先保存一下重新打开,可以用iw/2测试,这个时候绘制框和预览框应该是显眼的一长条,
    多个从视频位置都可以相互预览

<img width="815" height="631" alt="Img20260601101715360" src="https://github.com/user-attachments/assets/90e34b97-3cea-45bf-99d5-629e9013486e" />
<img width="350" height="781" alt="Img20260601103950813" src="https://github.com/user-attachments/assets/42ab4456-47aa-4b9f-9777-df95fb2b3a24" />


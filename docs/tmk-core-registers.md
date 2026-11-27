# 统一维护 CPU、FPU 和外设寄存器

打开设备 SVD 后，可以在 **CPU** 节点编辑 CMSIS-SVD 定义的处理器型号、修订号、字节序和功能标志。**内核寄存器**节点用于维护通过调试器寄存器 ID 访问的 CPU、FPU 等分组。每组可以添加寄存器并编辑 ID、位宽、说明和位域。外设和其他实际映射到总线地址的寄存器继续使用 SVD 外设节点。

## 从 TMKStudioIDE 导入和导出

在**工具**菜单中选择 **导入 TMK ISS 寄存器配置**，可以导入 TMK 寄存器 XML，或选择 TMKStudioIDE `plugins` 目录下的 `cn.com.tmkstudio.debug.core-1.0.0-SNAPSHOT.jar` 一次导入 CPU 和 FPU。保存为新的 SVD 后，内核寄存器与外设在同一文件中维护。右键点击内核组可以导出该组的 TMK XML。

也可以用 CLI 完成同样的流程。将示例中的 JAR 路径指向本机 TMKStudioIDE 的插件目录。

```powershell
svdstudio import-tmk-core device.svd unified.svd --jar path\to\cn.com.tmkstudio.debug.core-1.0.0-SNAPSHOT.jar
svdstudio info unified.svd --json
svdstudio export-tmk-core unified.svd TMS320C28XX c28xx.xml
svdstudio export-tmk-core unified.svd TMK_SIMULATOR_FPU c28xx-fpu.xml
```

手头只有独立配置文件时，导入命令可以使用 `--xml c28xx.xml c28xx-fpu.xml`。已有同 ID 的组时，CLI 需要显式传入 `--replace`。TMK XML 支持组 ID、寄存器 ID 和位宽，以及位域范围和访问标记。导出时遇到旧格式无法表达的寄存器复位值或其他属性，工具会报出涉及的 ID。

## SVD 表示和 ISS 加载

内核信息位于设备的 `vendorExtensions` 中，扩展命名空间为 `https://github.com/tricky2022/SVD_Studio/core-registers/v1`。扩展中的 `group`、`register` 和 `field` 分别保存组 ID、调试器寄存器 ID 和位域。位域使用从低位计数的偏移和宽度。不同组可以使用相同的寄存器 ID，例如 CPU 和 FPU 各自定义的 `R0L`。

```xml
<vendorExtensions>
  <ss:coreRegisters xmlns:ss="https://github.com/tricky2022/SVD_Studio/core-registers/v1">
    <ss:group name="ExampleCPU">
      <ss:register name="STATUS" size="32">
        <ss:fields>
          <ss:field>
            <ss:name>READY</ss:name>
            <ss:bitOffset>7</ss:bitOffset>
            <ss:bitWidth>1</ss:bitWidth>
            <ss:access>R</ss:access>
          </ss:field>
        </ss:fields>
      </ss:register>
    </ss:group>
  </ss:coreRegisters>
</vendorExtensions>
```

TMKStudioIDE 1.4.9 的 ISS Register 视图通过调试插件资源加载 `c28xx.xml` 和 `c28xx-fpu.xml`。该版本导入 SVD 时，SVD 中的外设用于内存映射寄存器，内核组仍由内置 XML 提供。导出的 XML 可用于 IDE 构建中的配置更新。要让 Register 视图直接从一个 SVD 加载内核组，IDE 需要在原来的配置加载入口读取这个扩展，并继续使用现有的调试器寄存器 ID 访问值。对没有该扩展的 SVD，IDE 可以继续使用原来的配置。

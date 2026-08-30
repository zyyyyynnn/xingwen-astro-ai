import type { ContentHash } from "@xingwen/domain";
import { Alert, AlertDescription, Button, Spinner } from "@xingwen/ui";
import { Download } from "@xingwen/ui/icons";
import { useEffect, useRef, useState } from "react";

import { downloadBytes } from "../presentation/browser-download";
import {
  openWwtSession,
  type WwtSceneReadback,
  type WwtSpec,
} from "./wwt-session";

interface WwtViewportProps {
  readonly spec: WwtSpec;
  readonly loadContent: (contentHash: ContentHash) => Promise<ArrayBuffer>;
}

function canvasPng(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    try {
      canvas.toBlob((blob) => {
        if (blob === null) {
          reject(new Error("浏览器未能从当前 WebGL 画布生成 PNG。"));
          return;
        }
        resolve(blob);
      }, "image/png");
    } catch {
      reject(
        new Error(
          "浏览器拒绝读取 WebGL 画布；场景可能受跨域污染或当前图形上下文不可导出。",
        ),
      );
    }
  });
}

export function WwtViewport(props: WwtViewportProps) {
  const { spec, loadContent } = props;
  const hostRef = useRef<HTMLDivElement>(null);
  const loadContentRef = useRef(loadContent);
  const sessionRef = useRef<ReturnType<typeof openWwtSession> | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [message, setMessage] = useState("正在初始化 WorldWide Telescope");
  const [readback, setReadback] = useState<WwtSceneReadback | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [captureState, setCaptureState] = useState<
    "idle" | "capturing" | "success" | "error"
  >("idle");
  const [captureMessage, setCaptureMessage] = useState<string | null>(null);
  const label =
    spec.mode === "fits_image"
      ? "FITS 图像交互视图"
      : "WorldWide Telescope 交互场景";

  useEffect(() => {
    loadContentRef.current = loadContent;
  }, [loadContent]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const session = openWwtSession(host);
    sessionRef.current = session;
    return () => {
      if (sessionRef.current === session) sessionRef.current = null;
      session.close();
    };
  }, [attempt]);

  useEffect(() => {
    const host = hostRef.current;
    const session = sessionRef.current;
    if (!host || !session) return;
    let active = true;
    setState("loading");
    setReadback(null);
    setCaptureState("idle");
    setCaptureMessage(null);
    setMessage("正在初始化 WorldWide Telescope");
    void session
      .render(spec, {
        loadContent: (contentHash) => loadContentRef.current(contentHash),
        onProgress: (nextMessage) => {
          if (active) setMessage(nextMessage);
        },
        onAsyncError: (error) => {
          if (!active) return;
          setState("error");
          setMessage(
            error instanceof Error ? error.message : "WWT 场景播放失败",
          );
        },
      })
      .then((nextReadback) => {
        if (!active) return;
        const canvas = host.querySelector("canvas");
        if (canvas) {
          canvas.tabIndex = 0;
          canvas.setAttribute("aria-label", `${label}画布`);
        }
        setReadback(nextReadback);
        setState("ready");
      })
      .catch((error: unknown) => {
        if (!active) return;
        setState("error");
        setMessage(
          error instanceof Error ? error.message : "WWT 场景初始化失败",
        );
      });
    return () => {
      active = false;
    };
  }, [attempt, label, spec]);

  const capture = async () => {
    const canvas = hostRef.current?.querySelector("canvas");
    if (!canvas) {
      setCaptureState("error");
      setCaptureMessage("交互画布尚未就绪，无法导出 PNG。");
      return;
    }
    setCaptureState("capturing");
    setCaptureMessage(null);
    try {
      const blob = await canvasPng(canvas);
      downloadBytes({
        bytes: await blob.arrayBuffer(),
        fileName:
          spec.mode === "fits_image" ? "fits-view.png" : "wwt-scene.png",
        mediaType: "image/png",
      });
      setCaptureState("success");
      setCaptureMessage("PNG 已下载。");
    } catch (error) {
      setCaptureState("error");
      setCaptureMessage(
        error instanceof Error ? error.message : "当前交互画布无法导出 PNG。",
      );
    }
  };

  return (
    <figure
      className="wwt-viewport"
      data-testid="wwt-viewport"
      data-state={state}
      aria-busy={state === "loading"}
    >
      <div
        ref={hostRef}
        className="wwt-viewport__canvas"
        role="region"
        aria-label={label}
        tabIndex={0}
      />
      {state === "ready" && readback !== null ? (
        <dl className="wwt-viewport__readback" aria-label="WWT 实际状态读取">
          {readback.centerCoordinates === null ? null : (
            <div>
              <dt>实际中心</dt>
              <dd>
                RA {readback.centerCoordinates.raHours.toFixed(4)}h · Dec{" "}
                {readback.centerCoordinates.decDegrees.toFixed(4)}°
              </dd>
            </div>
          )}
          {readback.fieldOfViewDegrees === null ? null : (
            <div>
              <dt>实际视场</dt>
              <dd>{readback.fieldOfViewDegrees.toFixed(3)}°</dd>
            </div>
          )}
          {readback.currentTime === null ? null : (
            <div>
              <dt>实际时间</dt>
              <dd>{readback.currentTime.slice(0, 19).replace("T", " ")} UTC</dd>
            </div>
          )}
        </dl>
      ) : null}
      {state === "loading" ? (
        <figcaption data-state={state}>
          <Spinner aria-hidden="true" />
          <span>{message}</span>
        </figcaption>
      ) : null}
      {state === "error" ? (
        <figcaption data-state={state}>
          <Alert variant="destructive">
            <AlertDescription>{message}</AlertDescription>
          </Alert>
          <Button
            type="button"
            variant="secondary"
            size="small"
            onClick={() => setAttempt((value) => value + 1)}
          >
            重新加载交互视图
          </Button>
        </figcaption>
      ) : null}
      {state === "ready" ? (
        <figcaption className="sr-only">
          {label}已加载，可使用键盘聚焦视图。
        </figcaption>
      ) : null}
      {state === "ready" ? (
        <div className="wwt-viewport__actions">
          <Button
            type="button"
            variant="secondary"
            size="small"
            disabled={captureState === "capturing"}
            onClick={() => void capture()}
          >
            <Download data-icon="inline-start" aria-hidden="true" />
            {captureState === "capturing" ? "正在生成 PNG" : "下载场景 PNG"}
          </Button>
          {captureMessage ? (
            <p
              role={captureState === "error" ? "alert" : "status"}
              data-state={captureState}
            >
              {captureMessage}
            </p>
          ) : null}
        </div>
      ) : null}
      <details className="wwt-viewport__fallback">
        <summary>查看文本与表格替代视图</summary>
        {spec.mode === "fits_image" ? (
          <dl>
            <div>
              <dt>拉伸</dt>
              <dd>{spec.stretch}</dd>
            </div>
            <div>
              <dt>色图</dt>
              <dd>{spec.colorMap}</dd>
            </div>
          </dl>
        ) : (
          <>
            <p>{spec.textAlternative}</p>
            <dl>
              <div>
                <dt>视图</dt>
                <dd>
                  {spec.view.kind === "coordinates"
                    ? `RA ${spec.view.center.raHours.toFixed(4)}h · Dec ${spec.view.center.decDegrees.toFixed(4)}°`
                    : `跟踪 ${spec.view.target}`}
                </dd>
              </div>
              <div>
                <dt>视场</dt>
                <dd>{spec.view.fieldOfViewDegrees}°</dd>
              </div>
              <div>
                <dt>相机滚转</dt>
                <dd>{spec.view.rollDegrees}°</dd>
              </div>
              <div>
                <dt>背景</dt>
                <dd>{spec.background}</dd>
              </div>
              <div>
                <dt>坐标网格</dt>
                <dd>
                  {spec.coordinateGrids.length > 0
                    ? spec.coordinateGrids
                        .map(
                          (grid) =>
                            `${grid.system}${grid.labels ? "（含标签）" : ""}`,
                        )
                        .join("、")
                    : "未启用"}
                </dd>
              </div>
              <div>
                <dt>时间控制</dt>
                <dd>
                  {spec.time.mode}
                  {spec.time.observedAt ? ` · ${spec.time.observedAt}` : ""}
                  {spec.time.rate !== null ? ` · ${spec.time.rate}×` : ""}
                </dd>
              </div>
              <div>
                <dt>观测者</dt>
                <dd>
                  {spec.observer === null
                    ? "未设置"
                    : `${spec.observer.latitudeDegrees}°, ${spec.observer.longitudeDegrees}° · ${spec.observer.elevationMeters} m`}
                </dd>
              </div>
              <div>
                <dt>前景</dt>
                <dd>
                  {spec.foreground === null
                    ? "未设置"
                    : `${spec.foreground.imageSet} · ${Math.round(spec.foreground.opacity * 100)}%`}
                </dd>
              </div>
            </dl>
            {spec.fitsLayers.length > 0 ? (
              <table>
                <caption>WWT FITS 图层</caption>
                <thead>
                  <tr>
                    <th scope="col">图层</th>
                    <th scope="col">透明度</th>
                  </tr>
                </thead>
                <tbody>
                  {spec.fitsLayers.map((layer, index) => (
                    <tr key={layer.layerId}>
                      <th scope="row">FITS 图层 {index + 1}</th>
                      <td>{layer.opacity}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p>当前场景没有 FITS 图层。</p>
            )}
            {spec.tableLayers.length > 0 ? (
              <table>
                <caption>WWT 表格图层</caption>
                <thead>
                  <tr>
                    <th scope="col">图层</th>
                    <th scope="col">坐标</th>
                  </tr>
                </thead>
                <tbody>
                  {spec.tableLayers.map((layer, index) => (
                    <tr key={layer.layerId}>
                      <th scope="row">表格图层 {index + 1}</th>
                      <td>
                        {layer.coordinates.kind} · {layer.coordinates.frame}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p>当前场景没有表格图层。</p>
            )}
            {spec.annotations.length > 0 ? (
              <table>
                <caption>WWT 场景标注</caption>
                <thead>
                  <tr>
                    <th scope="col">标注</th>
                    <th scope="col">类型</th>
                    <th scope="col">标签</th>
                    <th scope="col">坐标点</th>
                  </tr>
                </thead>
                <tbody>
                  {spec.annotations.map((annotation, index) => (
                    <tr key={annotation.annotationId}>
                      <th scope="row">
                        {annotation.label ?? `标注 ${index + 1}`}
                      </th>
                      <td>{annotation.kind}</td>
                      <td>{annotation.label ?? "未提供"}</td>
                      <td>{annotation.points.length}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p>当前场景没有标注。</p>
            )}
            {spec.tourSteps.length > 0 ? (
              <table>
                <caption>
                  WWT 场景步骤
                  {spec.tourAutoplay ? "（自动播放）" : ""}
                </caption>
                <thead>
                  <tr>
                    <th scope="col">步骤</th>
                    <th scope="col">视图</th>
                    <th scope="col">停留</th>
                  </tr>
                </thead>
                <tbody>
                  {spec.tourSteps.map((step, index) => (
                    <tr key={step.stepId}>
                      <th scope="row">第 {index + 1} 步</th>
                      <td>
                        {step.view.kind === "coordinates"
                          ? `RA ${step.view.center.raHours.toFixed(4)}h · Dec ${step.view.center.decDegrees.toFixed(4)}°`
                          : `跟踪 ${step.view.target}`}
                      </td>
                      <td>{step.holdSeconds} s</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p>当前场景没有场景步骤。</p>
            )}
          </>
        )}
      </details>
    </figure>
  );
}

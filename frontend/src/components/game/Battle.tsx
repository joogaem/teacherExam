"use client";
import { useEffect, useRef, forwardRef, useImperativeHandle } from "react";
import type PhaserType from "phaser";

// 문제 유형 → 몬스터
const ENEMY: Record<string, { emoji: string; name: string; size: number }> = {
  mcq: { emoji: "👾", name: "지식 슬라임", size: 52 },
  fill_blank: { emoji: "🤺", name: "빈칸 기사", size: 58 },
  matching: { emoji: "🗿", name: "혼동 골렘", size: 64 },
  essay: { emoji: "🐉", name: "서술형 드래곤", size: 84 },
};

export interface BattleHandle {
  spawnEnemy: (qType: string) => void;
  attack: (kill: boolean, gain: number) => void;
  hurt: () => void;
  defeat: () => void;
}

const W = 640;
const H = 210;
const GROUND = 175;
const HERO_X = 130;
const ENEMY_X = 500;

const Battle = forwardRef<BattleHandle, object>(function Battle(_props, ref) {
  const hostRef = useRef<HTMLDivElement>(null);
  const gameRef = useRef<PhaserType.Game | null>(null);
  // 씬에 노출할 메서드 모음 (씬 create 후 채워짐)
  const sceneApi = useRef<Partial<BattleHandle>>({});
  const pending = useRef<Array<() => void>>([]);

  const call = (fn: (api: Partial<BattleHandle>) => void) => {
    if (sceneApi.current.spawnEnemy) fn(sceneApi.current);
    else pending.current.push(() => fn(sceneApi.current));
  };

  useImperativeHandle(ref, () => ({
    spawnEnemy: (t) => call(api => api.spawnEnemy?.(t)),
    attack: (kill, gain) => call(api => api.attack?.(kill, gain)),
    hurt: () => call(api => api.hurt?.()),
    defeat: () => call(api => api.defeat?.()),
  }));

  useEffect(() => {
    let destroyed = false;

    (async () => {
      const Phaser = (await import("phaser")).default;
      if (destroyed || !hostRef.current) return;

      class BattleScene extends Phaser.Scene {
        hero!: PhaserType.GameObjects.Text;
        enemy: PhaserType.GameObjects.Text | null = null;
        enemyLabel: PhaserType.GameObjects.Text | null = null;
        heroTween!: PhaserType.Tweens.Tween;

        create() {
          const g = this.add.graphics();
          g.lineStyle(2, 0x3f3f5e);
          g.lineBetween(20, GROUND, W - 20, GROUND);

          this.hero = this.add.text(HERO_X, GROUND, "🧙", { fontSize: "60px" }).setOrigin(0.5, 1);
          this.heroTween = this.tweens.add({
            targets: this.hero, y: GROUND - 7, duration: 750,
            yoyo: true, repeat: -1, ease: "Sine.inOut",
          });

          sceneApi.current = {
            spawnEnemy: this.spawnEnemy.bind(this),
            attack: this.attackAnim.bind(this),
            hurt: this.hurtAnim.bind(this),
            defeat: this.defeatAnim.bind(this),
          };
          pending.current.forEach(fn => fn());
          pending.current = [];
        }

        spawnEnemy(qType: string) {
          const spec = ENEMY[qType] ?? ENEMY.mcq;
          this.enemy?.destroy();
          this.enemyLabel?.destroy();

          this.enemy = this.add.text(W + 60, GROUND, spec.emoji, { fontSize: `${spec.size}px` })
            .setOrigin(0.5, 1);
          this.enemyLabel = this.add.text(ENEMY_X, 26, spec.name, {
            fontSize: "15px", color: "#fbbf24", fontStyle: "bold",
          }).setOrigin(0.5).setAlpha(0);

          this.tweens.add({ targets: this.enemy, x: ENEMY_X, duration: 450, ease: "Back.out" });
          this.tweens.add({ targets: this.enemyLabel, alpha: 1, duration: 300, delay: 350 });
          this.tweens.add({
            targets: this.enemy, y: GROUND - 6, duration: 850,
            yoyo: true, repeat: -1, ease: "Sine.inOut", delay: 480,
          });
        }

        attackAnim(kill: boolean, gain: number) {
          const enemy = this.enemy;
          if (!enemy) return;
          // 용사 돌진
          this.tweens.add({
            targets: this.hero, x: ENEMY_X - 70, duration: 170, ease: "Cubic.in",
            yoyo: true,
            onYoyo: () => {
              this.cameras.main.shake(130, 0.012);
              this.slash(ENEMY_X - 28, GROUND - 46);
              if (gain > 0) this.floatText(ENEMY_X, GROUND - 95, `+${gain}`, "#34d399");
              if (kill) {
                this.tweens.killTweensOf(enemy);
                this.tweens.add({
                  targets: enemy, alpha: 0, angle: 100, y: GROUND + 36,
                  duration: 480, ease: "Cubic.in",
                  onComplete: () => this.floatText(ENEMY_X, GROUND - 60, "처치!", "#fbbf24"),
                });
                if (this.enemyLabel) this.tweens.add({ targets: this.enemyLabel, alpha: 0, duration: 300 });
              } else {
                enemy.setTintFill(0xffffff);
                this.time.delayedCall(110, () => enemy.clearTint());
              }
            },
          });
        }

        hurtAnim() {
          const enemy = this.enemy;
          if (enemy) {
            this.tweens.add({
              targets: enemy, x: HERO_X + 70, duration: 170, ease: "Cubic.in",
              yoyo: true,
              onYoyo: () => {
                this.cameras.main.shake(200, 0.018);
                this.hero.setTintFill(0xff5555);
                this.time.delayedCall(160, () => this.hero.clearTint());
                this.floatText(HERO_X, GROUND - 90, "-1 ❤️", "#f87171");
              },
            });
          } else {
            this.cameras.main.shake(200, 0.018);
            this.floatText(HERO_X, GROUND - 90, "-1 ❤️", "#f87171");
          }
        }

        defeatAnim() {
          this.heroTween.stop();
          this.tweens.add({
            targets: this.hero, angle: 90, y: GROUND + 16, alpha: 0.4,
            duration: 600, ease: "Cubic.in",
          });
        }

        // 베기 이펙트 — 짧은 호 모양 선
        slash(x: number, y: number) {
          const s = this.add.text(x, y, "⚡", { fontSize: "40px" }).setOrigin(0.5).setAngle(-20);
          this.tweens.add({
            targets: s, alpha: 0, scale: 1.6, duration: 260,
            onComplete: () => s.destroy(),
          });
        }

        floatText(x: number, y: number, msg: string, color: string) {
          const t = this.add.text(x, y, msg, {
            fontSize: "20px", color, fontStyle: "bold",
          }).setOrigin(0.5);
          this.tweens.add({
            targets: t, y: y - 42, alpha: 0, duration: 900, ease: "Cubic.out",
            onComplete: () => t.destroy(),
          });
        }
      }

      gameRef.current = new Phaser.Game({
        type: Phaser.AUTO,
        parent: hostRef.current,
        width: W,
        height: H,
        transparent: true,
        scene: BattleScene,
        scale: {
          mode: Phaser.Scale.FIT,
          autoCenter: Phaser.Scale.CENTER_HORIZONTALLY,
        },
      });
    })();

    return () => {
      destroyed = true;
      sceneApi.current = {};
      gameRef.current?.destroy(true);
      gameRef.current = null;
    };
  }, []);

  return <div ref={hostRef} className="w-full max-w-2xl mx-auto" style={{ minHeight: 100 }} />;
});

export default Battle;

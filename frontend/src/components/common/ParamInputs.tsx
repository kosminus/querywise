import { NumberInput, Stack, Switch, TextInput } from '@mantine/core';
import type { ParamDef } from '../../types/api';

/**
 * Renders typed input controls for a set of param/filter definitions.
 * Shared by the saved-query run drawer and the dashboard filters bar.
 * Values are held by the parent; `onChange(name, value)` reports edits.
 */
export function ParamInputs({
  params,
  values,
  onChange,
  inline = false,
}: {
  params: ParamDef[];
  values: Record<string, unknown>;
  onChange: (name: string, value: unknown) => void;
  inline?: boolean;
}) {
  const Wrapper = inline ? 'div' : Stack;
  const wrapperProps = inline
    ? { style: { display: 'flex', gap: 12, flexWrap: 'wrap' as const, alignItems: 'flex-end' } }
    : { gap: 'xs' as const };

  return (
    <Wrapper {...wrapperProps}>
      {params.map((p) => {
        const label = p.label || p.name;
        if (p.type === 'number') {
          return (
            <NumberInput
              key={p.name}
              label={label}
              value={values[p.name] as number | undefined}
              onChange={(v) => onChange(p.name, v)}
            />
          );
        }
        if (p.type === 'boolean') {
          return (
            <Switch
              key={p.name}
              label={label}
              checked={!!values[p.name]}
              onChange={(e) => onChange(p.name, e.currentTarget.checked)}
            />
          );
        }
        return (
          <TextInput
            key={p.name}
            label={label}
            placeholder={p.type === 'date' ? 'YYYY-MM-DD' : undefined}
            value={(values[p.name] as string) ?? ''}
            onChange={(e) => onChange(p.name, e.currentTarget.value)}
          />
        );
      })}
    </Wrapper>
  );
}
